"""Anki's local web server (aqt.mediasrv) without a socket.

A browser tab can't listen on a port. shell/sw.js catches the requests of
Kioku's iframes and the page relays them here; each one runs on a worker
thread through Anki's Flask app, as Anki's own server thread would run it.
Anki builds its URLs as http://127.0.0.1:<port>/... (mw.serverURL(),
webBundlePath, its CSPs); the page may be served from anywhere
(127.0.0.1, localhost, a real domain), so they are pointed at the page's
own origin, where the service worker sees them. Anki's Flask app still
gets 127.0.0.1 requests, which its host check wants.

Responses are adapted for iframes: Anki forbids framing its pages
(frame-ancestors 'none'), and Kioku's scripts are added to every HTML page
through /_anki/__kioku/init.js (an /_anki/ URL passes the editor's
script-src). Running JavaScript in a page from outside (QWebEngine's
runJavaScript) counts as eval for the page's CSP, so pages that restrict
scripts also get 'unsafe-eval'.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from urllib.parse import urlsplit

import _kioku_web

logger = logging.getLogger("kioku.http")

PREFIX = "/_anki/__kioku/"
_port = 0
# the app page's, e.g. http://127.0.0.1:8765 or https://kioku.example.com
origin = ""
# pages given to WebView.load_html(), by key: (html, base URL)
html_pages: dict[str, tuple[str, str | None]] = {}

# first script of every page: pulls in the scripts of the view showing it
INIT_JS = r"""
(function () {
    if (window.__kiokuInit) return;
    window.__kiokuInit = true;
    var frame = window.frameElement;
    if (!frame || !frame.dataset.kioku) return;
    document.write('<script src="/_anki/__kioku/view/' + frame.dataset.kioku + "/" +
        frame.dataset.gen + '.js"><\/script>');
})();
"""

_HEAD_RE = re.compile(rb"<head\b[^>]*>", re.IGNORECASE)
_DOCTYPE_RE = re.compile(rb"^\s*<!doctype[^>]*>", re.IGNORECASE)
_TEXT_TYPES = ("text/html", "text/css", "text/javascript", "application/javascript", "application/json")
_META_CSP_RE = re.compile(
    rb'(<meta http-equiv="content-security-policy" content="script-src [^"]*)"', re.IGNORECASE
)


def setup(page_origin: str) -> None:
    """Make aqt.mediasrv's server thread a no-op that reports the page's
    port, and Anki's URLs the page's origin."""
    global _port, origin
    import aqt.main
    import aqt.mediasrv
    import aqt.webview

    origin = page_origin
    _port = urlsplit(origin).port or (443 if origin.startswith("https:") else 80)

    def run(self) -> None:  # type: ignore[no-untyped-def]
        logger.info("Anki's pages are served in-process on port %d", _port)
        self._ready.set()

    aqt.mediasrv.MediaServer.run = run
    aqt.mediasrv.MediaServer.getPort = lambda self: _port
    aqt.mediasrv.MediaServer.shutdown = lambda self: None
    aqt.main.AnkiQt.serverURL = lambda self: origin + "/"

    def web_bundle_path(cls: type, path: str) -> str:
        return origin + (path if path.startswith("/") else "/_anki/" + path)

    aqt.webview.AnkiWebView.webBundlePath = classmethod(web_bundle_path)  # type: ignore[assignment]


def local_url(url: str) -> str:
    """`url` with Anki's own origins (127.0.0.1 or localhost, as add-ons
    like AMBOSS build them) replaced by the page's."""
    for local in (f"http://127.0.0.1:{_port}", f"http://localhost:{_port}"):
        if url.startswith(local + "/") or url == local:
            return origin + url[len(local) :]
    return url


def _local_text(data: bytes) -> bytes:
    for local in (f"http://127.0.0.1:{_port}", f"http://localhost:{_port}"):
        data = data.replace(local.encode(), origin.encode())
    return data


def handle(event: dict) -> None:
    try:
        status, headers, body = _serve(event)
    except Exception:
        logger.exception("serving %s", event.get("url"))
        status, headers, body = 500, [("Content-Type", "text/plain")], b"Kioku: request failed"
    _kioku_web.respond(event["id"], status, json.dumps(headers).encode(), body)


def _serve(event: dict) -> tuple[int, list[tuple[str, str]], bytes]:
    url = urlsplit(event["url"])
    if url.path.startswith(PREFIX):
        return _kioku_file(url.path[len(PREFIX) :])

    import aqt.mediasrv

    headers = {
        k: v for k, v in event["headers"].items() if k.lower() not in ("host", "origin")
    }
    client = aqt.mediasrv.app.test_client()
    resp = client.open(
        # still percent-encoded: werkzeug decodes the path itself, as Anki's
        # server (waitress) does on the desktop. Decoded here first, a media
        # file whose name has "#" or "%xx" in it (the editor's src="a%23b.png")
        # was cut at the "#" or decoded twice, and didn't show
        url.path,
        base_url=f"http://127.0.0.1:{_port}",
        query_string=url.query,
        method=event["method"],
        headers=headers,
        data=base64.b64decode(event.get("body") or ""),
    )
    body = resp.get_data()
    out = []
    for name, value in resp.headers.items():
        lname = name.lower()
        if lname in ("content-length", "x-frame-options"):
            continue
        if lname == "content-security-policy":
            value = _csp(value)
        elif lname == "location":
            value = local_url(value)
        out.append((name, value))
    if resp.mimetype in _TEXT_TYPES:
        body = _local_text(body)
    if resp.mimetype == "text/html":
        body = _inject(body)
    return resp.status_code, out, body


def _csp(value: str) -> str:
    value = _local_text(value.encode()).decode()
    value = value.replace("frame-ancestors 'none'", "frame-ancestors 'self'")
    if "script-src" in value and "'unsafe-eval'" not in value:
        value = re.sub(r"script-src([^;]*)", r"script-src\1 'unsafe-eval'", value, count=1)
    return value


def _inject(html: bytes, base: str | None = None) -> bytes:
    html = _META_CSP_RE.sub(rb"\1 'unsafe-eval'\"", html, count=1)
    tags = f'<script src="{PREFIX}init.js"></script>'
    if base:
        tags = f'<base href="{base}">' + tags
    tag = tags.encode()
    if m := _HEAD_RE.search(html):
        return html[: m.end()] + tag + html[m.end() :]
    if m := _DOCTYPE_RE.match(html):
        return html[: m.end()] + tag + html[m.end() :]
    return tag + html


def _js(text: str) -> tuple[int, list[tuple[str, str]], bytes]:
    return 200, [("Content-Type", "text/javascript; charset=utf-8"), ("Cache-Control", "no-store")], text.encode()


def _kioku_file(name: str) -> tuple[int, list[tuple[str, str]], bytes]:
    from .webview import _views

    if name == "init.js":
        return _js(INIT_JS)
    parts = name.split("/")
    if parts[0] == "view" and len(parts) >= 3:
        view = _views.get(int(parts[1]))
        if view is None:
            return _js("")
        if len(parts) == 3:
            return _js(view.page_script(int(parts[2].removesuffix(".js"))))
        return _js(view.user_script(int(parts[3].removesuffix(".js"))))
    if parts[0] == "html" and len(parts) == 2 and parts[1] in html_pages:
        html, base = html_pages[parts[1]]
        page = _local_text(html.encode())
        return 200, [("Content-Type", "text/html; charset=utf-8")], _inject(page, base and local_url(base))
    return 404, [("Content-Type", "text/plain")], b"not found"
