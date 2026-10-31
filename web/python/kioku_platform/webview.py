"""The web view backend: an <iframe> on the page, embedded into the Qt widget
as a foreign window (Qt for WebAssembly wraps HTML elements given to
QWindow.fromWinId), so Qt places, sizes and stacks it.

Pages come from the service worker (see http.py). Kioku's scripts reach a
page through http.INIT_JS; the page talks back through
window.parent.__kiokuWeb.
"""

from __future__ import annotations

import itertools
import json
import logging
import weakref
from typing import Any, Callable

import _kioku_web
from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtGui import QWindow
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from . import http, web

logger = logging.getLogger("kioku.webview")

_ids = itertools.count(1)
_views: "weakref.WeakValueDictionary[int, WebView]" = weakref.WeakValueDictionary()

AT_DOCUMENT_START = 0


def _route(event: dict) -> None:
    view = _views.get(event.get("view", 0))
    if view is not None:
        view._event(event)


_callback_ids = itertools.count(1)

for _type in ("load", "message", "channel", "navigate", "eval"):
    web.listen(_type, _route)


def set_cookie(url: str, header: str) -> None:
    pass


def delete_cookies(domain: str, name: str | None) -> None:
    pass


class _Resizes(QObject):
    """Qt for WebAssembly sets only the width of a foreign window's element;
    keep the iframe as tall as its container."""

    def __init__(self, view_id: int, parent: QObject) -> None:
        super().__init__(parent)
        self.view_id = view_id

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if event is not None and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            web.js("size", self.view_id, obj.height())  # type: ignore[union-attr]
        return False


class WebView:
    """Callbacks (on_*) are overridden by kioku.webengine."""

    # defines window.__kiokuNative for kioku.webscripts.PRELUDE (see
    # bridge() in shell/kioku-web.js)
    BRIDGE = r"""
(function () {
    if (!window.__kiokuNative) window.parent.__kiokuWeb.bridge(window);
})();
"""

    @staticmethod
    def prepare_host(widget: QWidget) -> None:
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

    def __init__(self) -> None:
        self.id = next(_ids)
        self.gen = 0
        self._url = ""
        self._scripts: list[tuple[str, int, bool]] = []
        self._callbacks: dict[int, Callable[[Any], None]] = {}
        self._container: QWidget | None = None
        self._host: QWidget | None = None
        web.js("create", self.id)
        _views[self.id] = self

    # Scripts (served by http.py) -------------------------------------------

    def set_user_scripts(self, scripts: list[tuple[str, int, bool]]) -> None:
        # kioku.webengine's auth script adds Anki's headers to requests for
        # host 127.0.0.1; here Anki's server is the page's origin
        self._scripts = [
            (js.replace("hostname==='127.0.0.1'", f"origin==={json.dumps(http.origin)}"), when, main)
            for js, when, main in scripts
        ]

    def page_script(self, gen: int) -> str:
        """Loads the scripts as separate files, so each runs at global scope
        (Anki's bridge declares `var pycmd`) and an error in one doesn't stop
        the others: document-start ones right away, the rest at
        DOMContentLoaded (QWebEngineScript.DocumentReady)."""
        start, ready = [], []
        for i, (_, when, _) in enumerate(self._scripts):
            url = f"{http.PREFIX}view/{self.id}/{gen}/{i}.js"
            (start if when == AT_DOCUMENT_START else ready).append(url)
        tags = "".join(f'<script src="{url}"></script>' for url in start)
        return (
            f"document.write({json.dumps(tags)});\n"
            'document.addEventListener("DOMContentLoaded", function () {\n'
            f"    {json.dumps(ready)}.forEach(function (url) {{\n"
            '        var s = document.createElement("script");\n'
            "        s.src = url;\n"
            "        s.async = false;\n"
            "        document.head.appendChild(s);\n"
            "    });\n"
            "});\n"
        )

    def user_script(self, index: int) -> str:
        return self._scripts[index][0] if index < len(self._scripts) else ""

    # Loading ---------------------------------------------------------------

    def load_url(self, url: str, headers: dict[str, str] | None = None) -> None:
        self.gen += 1
        self._url = url
        self.on_load_started()
        # Anki's and add-ons' 127.0.0.1/localhost URLs: only the page's own
        # origin reaches the service worker
        web.js("load", self.id, http.local_url(url), self.gen)

    def load_html(self, html: str, base_url: str | None) -> None:
        key = f"{self.id}-{self.gen + 1}"
        http.html_pages[key] = (html, base_url)
        # keep only the latest page of each view
        for old in [k for k in http.html_pages if k.startswith(f"{self.id}-") and k != key]:
            del http.html_pages[old]
        self.load_url(f"{http.origin}{http.PREFIX}html/{key}")
        self._url = base_url or "about:blank"

    def reload(self) -> None:
        web.js("reload", self.id)

    def stop(self) -> None:
        pass

    def back(self) -> None:
        web.js("go", self.id, -1)

    def forward(self) -> None:
        web.js("go", self.id, 1)

    def url(self) -> str:
        return self._url

    def title(self) -> str:
        return web.js("title", self.id)

    def history(self) -> dict[str, str]:
        return {}

    # JavaScript --------------------------------------------------------------

    def evaluate(self, js: str, callback: Callable[[Any], None] | None) -> None:
        # the result comes back as an event, after the messages the script
        # sent: Anki's saveNow() relies on that order (field saves first)
        cb = next(_callback_ids) if callback is not None else 0
        if cb:
            self._callbacks[cb] = callback  # type: ignore[assignment]
        web.js("eval", self.id, js, cb)

    def print_pdf(self, path: str) -> None:
        self.on_pdf_finished(path, False)

    # Appearance --------------------------------------------------------------

    def set_background(self, r: float, g: float, b: float, a: float) -> None:
        web.js("background", self.id, f"rgba({round(r * 255)},{round(g * 255)},{round(b * 255)},{a})")

    def set_zoom(self, factor: float) -> None:
        web.js("zoom", self.id, factor)

    # Hosting ---------------------------------------------------------------

    def attach(self, widget: QWidget) -> None:
        if self._host is widget and self._container is not None:
            self._container.show()
            return
        handle = _kioku_web.element_handle(self.id)
        if handle is None:
            return
        window = QWindow.fromWinId(handle)
        container = QWidget.createWindowContainer(window, widget)
        container.installEventFilter(_Resizes(self.id, container))
        layout = widget.layout()
        if layout is not None:
            layout.addWidget(container)
        container.show()
        self._container = container
        self._host = widget
        QTimer.singleShot(0, lambda: web.js("adopt", self.id))

    def detach(self) -> None:
        if self._container is not None:
            self._container.hide()

    def close(self) -> None:
        _views.pop(self.id, None)
        try:
            web.js("destroy", self.id)
        except RuntimeError:
            pass

    # Events from the page ----------------------------------------------------

    def _event(self, event: dict) -> None:
        kind = event["type"]
        if kind == "load":
            # gen 0 is the empty document of a new iframe; older gens are
            # pages replaced by a newer load
            if event.get("gen") == self.gen and self.gen:
                url = event.get("url", "")
                if url and http.PREFIX not in url:
                    self._url = url
                self.on_load_finished(True)
        elif kind == "message":
            if event["name"] == "console":
                self.on_console(json.loads(event["text"]))
            elif event["name"] == "selection":
                self.on_selection(event["text"])
            elif event["name"] == "tap":
                tap = json.loads(event["text"])
                self.on_tap(tap["x"], tap["y"])
        elif kind == "channel":
            self._channel(event)
        elif kind == "eval":
            callback = self._callbacks.pop(event["cb"], None)
            if callback is not None:
                try:
                    value = json.loads(event["value"]) if event.get("value") else None
                except ValueError:
                    value = None
                callback(value)
        elif kind == "navigate":
            if self.on_navigation(event["url"], 0, True):
                self.load_url(event["url"])

    def _channel(self, event: dict) -> None:
        if event.get("gen") != self.gen:
            # from the previous document: Anki would take its "domDone" for
            # the page now loading and run queued JavaScript on the old one
            web.js("resolve", self.id, event["call"], True, "null")
            return
        try:
            call = json.loads(event["text"])
            result = self.on_channel_call(call["obj"], call["method"], call.get("args", []))
            ok, value = True, json.dumps(result)
        except Exception as e:
            logger.exception("channel call failed")
            ok, value = False, str(e)
        web.js("resolve", self.id, event["call"], ok, value)

    # Callbacks, overridden by the owner -------------------------------------

    def on_console(self, entry: dict) -> None: ...
    def on_selection(self, text: str) -> None: ...
    def on_tap(self, x: float, y: float) -> None: ...
    def on_channel_call(self, obj: str, method: str, args: list) -> Any: ...
    def on_navigation(self, url: str, nav_type: int, main_frame: bool) -> bool:
        return True
    def on_load_started(self) -> None: ...
    def on_load_finished(self, ok: bool) -> None: ...
    def on_alert(self, text: str) -> None: ...
    def on_pdf_finished(self, path: str, ok: bool) -> None: ...
    def on_confirm(self, text: str) -> bool:
        return False
