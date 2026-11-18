"""The QtWebEngine stand-in (kioku.webengine) as add-ons use it, over a fake
platform web view. The AMBOSS add-on is the model: a named profile subclass
with a parent keyword, cookies set from Python, and page history."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QDateTime, QObject, QTimer, QUrl, pyqtSlot
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWidgets import QApplication

from kioku import webengine, webscripts

app = QApplication.instance() or QApplication([])


class AddonProfile(webengine.QWebEngineProfile):
    def __init__(self, storage_name: str, parent: QObject | None = None) -> None:
        super().__init__(storage_name, parent=parent)
        self.added: list[str] = []
        self.cookieStore().cookieAdded.connect(
            lambda c: self.added.append(bytes(c.name()).decode())
        )


def auth_cookie() -> QNetworkCookie:
    cookie = QNetworkCookie(b"token", b"secret")
    cookie.setDomain(".example.com")
    cookie.setPath("/")
    cookie.setSecure(True)
    cookie.setHttpOnly(True)
    cookie.setExpirationDate(QDateTime.fromSecsSinceEpoch(2_000_000_000))
    return cookie


def test_named_profile_with_parent_keyword(platform) -> None:
    owner = QObject()
    profile = AddonProfile("amboss", parent=owner)
    assert profile.parent() is owner
    assert profile.storageName() == "amboss"
    assert not profile.isOffTheRecord()
    assert webengine.QWebEngineProfile.defaultProfile().isOffTheRecord()


def test_cookies_reach_the_platform(platform) -> None:
    profile = AddonProfile("amboss")
    store = profile.cookieStore()
    store.setCookie(auth_cookie())
    assert profile.added == ["token"]
    kind, url, header = platform.cookie_calls[-1]
    assert (kind, url) == ("set", "https://example.com/")
    assert header.startswith("token=secret;")
    assert "HttpOnly" in header and "secure" in header.lower()
    assert "domain=.example.com" in header

    store.loadAllCookies()
    assert profile.added == ["token", "token"]

    store.deleteAllCookies()
    assert platform.cookie_calls[-1] == ("delete", ".example.com", None)
    store.loadAllCookies()
    assert profile.added == ["token", "token"]


def test_cookie_without_domain_takes_the_origin(platform) -> None:
    store = AddonProfile("x").cookieStore()
    store.setCookie(QNetworkCookie(b"a", b"1"), QUrl("https://site.test/page"))
    assert platform.cookie_calls[-1][:2] == ("set", "https://site.test/page")
    assert "domain=site.test" in platform.cookie_calls[-1][2]


def test_page_with_profile_and_history(platform) -> None:
    profile = AddonProfile("amboss")
    parent = QObject()
    page = webengine.QWebEnginePage(profile, parent)
    assert page.profile() is profile and page.parent() is parent
    page2 = webengine.QWebEnginePage(profile=profile, parent=parent)
    assert page2.profile() is profile and page2.parent() is parent

    history = page.history()
    assert not history.canGoBack()
    assert not history.backItem().url().toString()
    page._web.state = {"back": "https://a.test/1", "forward": ""}
    assert history.canGoBack() and not history.canGoForward()
    assert history.backItem().url().toString() == "https://a.test/1"
    history.back()
    assert page._web.calls[-1] == "back"


def test_set_html_has_viewport_from_the_start() -> None:
    # Anki's stdHtml page: the meta right after <head>, the phone CSS after
    # the page's own style sheets
    page = (
        "<!doctype html>\n<html><head><title>x</title>"
        "<link rel=stylesheet href=deckbrowser.css></head><body></body></html>"
    )
    out = webscripts.with_viewport(page)
    assert out.startswith("<!doctype html>")
    assert out.index("<head>") < out.index('name="viewport"') < out.index("<title>")
    assert out.index("deckbrowser.css") < out.index('id="kioku-phone"') < out.index("</head>")
    assert webscripts.with_viewport(out) == out
    # a fragment without <head>: after the doctype, never before it
    out = webscripts.with_viewport("<!DOCTYPE html><p>hi</p>")
    assert out.startswith("<!DOCTYPE html><meta")
    assert webscripts.with_viewport("<p>hi</p>").startswith("<meta")
    # a page with its own viewport keeps it
    own = "<head><meta name=viewport content='width=500'></head>"
    out = webscripts.with_viewport(own)
    assert out.count("viewport") == 1 and 'id="kioku-phone"' in out


def test_url_changes_when_the_new_page_is_there(platform) -> None:
    # the Incremento add-on loads its reader only when url() isn't the reader's
    # yet, and otherwise talks to the page right away
    page = webengine.QWebEnginePage()
    platform_url = {"url": "file:///old.html"}
    page._web.url = lambda: platform_url["url"]
    page._web.title = lambda: ""
    # the platform views report the requested URL as soon as a load starts
    page._web.load_url = lambda url, headers: platform_url.update(url=url)
    changed: list[str] = []
    page.urlChanged.connect(lambda url: changed.append(url.toString()))

    page.load(QUrl("file:///new.html"))
    assert page.url().toString() == "file:///old.html"
    assert page.requestedUrl().toString() == "file:///new.html"
    assert changed == []

    page._on_load_finished(True)
    assert page.url().toString() == "file:///new.html"
    assert page.requestedUrl().toString() == "file:///new.html"
    assert changed == ["file:///new.html"]


class Bridge(QObject):
    """Like aqt.webview.Bridge: one slot, plus what a Python object has."""

    def __init__(self) -> None:
        super().__init__()
        self.cmds: list[str] = []
        self.secret = "token"

    @pyqtSlot(str, result=str)
    def cmd(self, text: str) -> str:
        self.cmds.append(text)
        return "ok:" + text

    def helper(self) -> str:
        return "not a slot"

    @pyqtSlot(str, name="renamed")
    def real_slot(self, text: str) -> None:
        pass

    def renamed(self, text: str) -> str:
        return "a plain method that shares the slot's Qt name"

    @pyqtSlot(result=str)
    def overridden(self) -> str:
        return "decorated"

    @pyqtSlot()
    def _hidden(self) -> None:
        pass


class Sub(Bridge):
    def overridden(self) -> str:  # not decorated again
        return "override"


def channel_page() -> tuple[webengine.QWebEnginePage, Bridge]:
    page = webengine.QWebEnginePage()
    bridge = Bridge()
    page.setWebChannel(webengine.QWebChannel())
    page.webChannel().registerObject("py", bridge)
    return page, bridge


def test_channel_calls_a_slot(platform) -> None:
    page, bridge = channel_page()
    assert page._web.on_channel_call("py", "cmd", ["hi"]) == "ok:hi"
    assert bridge.cmds == ["hi"]


def test_channel_refuses_what_is_not_a_slot(platform) -> None:
    page, bridge = channel_page()
    for method in ("helper", "secret", "renamed", "_hidden", "__class__", "deleteLater", "setParent"):
        with pytest.raises(RuntimeError, match="has no slot"):
            page._web.on_channel_call("py", method, [])
    assert bridge.cmds == []


def test_channel_refuses_a_subframe(platform) -> None:
    # a card can embed a page from another site; only the main frame of a
    # page has the bridge, as in Qt WebEngine
    page, bridge = channel_page()
    with pytest.raises(RuntimeError, match="main frame"):
        page._web.on_channel_call("py", "cmd", ["hi"], False)
    assert bridge.cmds == []
    assert page._web.on_channel_call("py", "cmd", ["hi"], True) == "ok:hi"


def test_bridge_and_token_scripts_run_in_the_main_frame_only(platform, monkeypatch) -> None:
    page = webengine.QWebEnginePage()
    installed: list[tuple] = []
    page._web.set_user_scripts = installed.extend
    monkeypatch.setattr(page._profile, "_headers_for", lambda url, api=False: {"Authorization": "Bearer secret"})
    page.setHtml("<p>x</p>")
    by_source = {source: main_only for source, _when, main_only in installed}
    assert any("Bearer secret" in s for s in by_source)
    for source, main_only in by_source.items():
        if source in (webengine.platform.WebView.BRIDGE, webscripts.PRELUDE) or "Bearer secret" in source:
            assert main_only, source[:40]


NODE_PAGE = """
globalThis.window = globalThis;
globalThis.location = {href: "http://127.0.0.1:8080/page"};
const sent = [];
window.fetch = (input, init) => {
  const url = input instanceof Request ? input.url : String(input);
  sent.push(["fetch", url, [...new Headers(init && init.headers)]]);
};
globalThis.XMLHttpRequest = class {
  open(m, u) { this.u = String(u); this.h = []; }
  send() { sent.push(["xhr", this.u, this.h]); }
  setRequestHeader(k, v) { this.h.push([k.toLowerCase(), v]); }
};
%s
%s
console.log(JSON.stringify(sent));
"""

TOKEN = [["authorization", "Bearer secret"]]


def run_page(page_js: str) -> list:
    script = webengine._auth_script({"Authorization": "Bearer secret"}, "http://127.0.0.1:8080")
    out = subprocess.run(
        ["node", "-e", NODE_PAGE % (script, page_js)], capture_output=True, text=True, check=True
    ).stdout
    return json.loads(out)


def test_token_goes_to_anki_server_only() -> None:
    # Anki 26.09's interceptor matches the server's host and port
    assert run_page(
        """
        fetch("http://127.0.0.1:8080/api");
        fetch("/relative", {headers: {"X-Own": "1"}});
        fetch("http://127.0.0.1:9999/api");
        fetch("https://example.com/api");
        const x = new XMLHttpRequest(); x.open("GET", "http://127.0.0.1:8080/api"); x.send();
        const y = new XMLHttpRequest(); y.open("GET", "http://127.0.0.1:9999/"); y.send();
        const z = new XMLHttpRequest(); z.open("GET", "/rel"); z.send();
        """
    ) == [
        ["fetch", "http://127.0.0.1:8080/api", TOKEN],
        ["fetch", "/relative", [["authorization", "Bearer secret"], ["x-own", "1"]]],
        ["fetch", "http://127.0.0.1:9999/api", []],
        ["fetch", "https://example.com/api", []],
        ["xhr", "http://127.0.0.1:8080/api", TOKEN],
        ["xhr", "http://127.0.0.1:9999/", []],
        ["xhr", "/rel", TOKEN],
    ]


def test_origin_is_spelled_like_url_origin() -> None:
    assert webengine._origin(QUrl("http://127.0.0.1:8080/x")) == "http://127.0.0.1:8080"
    assert webengine._origin(QUrl("http://127.0.0.1:80/x")) == "http://127.0.0.1"
    assert webengine._origin(QUrl("https://a.test/")) == "https://a.test"
    assert webengine._origin(QUrl("http://[::1]:8000/")) == "http://[::1]:8000"
    assert webengine._origin(QUrl("http://bücher.test/")) == "http://xn--bcher-kva.test"


def test_channel_calls_the_decorated_method_like_qt_does(platform) -> None:
    # PyQt invokes the slot that was decorated, even when a subclass overrides
    # the method without pyqtSlot
    page = webengine.QWebEnginePage()
    page.setWebChannel(webengine.QWebChannel())
    page.webChannel().registerObject("py", Sub())
    assert page._web.on_channel_call("py", "overridden", []) == "decorated"


def test_channel_does_not_call_a_python_override_of_a_qt_slot(platform) -> None:
    called: list[str] = []

    class Timer(QTimer):
        def stop(self) -> None:  # type: ignore[override]
            called.append("override")

    timer = Timer()
    page = webengine.QWebEnginePage()
    page.setWebChannel(webengine.QWebChannel())
    page.webChannel().registerObject("t", timer)
    timer.start(1000)
    page._web.on_channel_call("t", "stop", [])
    assert called == []
    assert not timer.isActive()


def _anki_auth_interceptor(server: str):  # type: ignore[no-untyped-def]
    """The installed Anki's AuthInterceptor and _is_internal_url, run against
    this stand-in's classes (aqt.webview itself needs Qt WebEngine)."""
    import ast
    import importlib.util
    import types

    path = os.path.join(os.path.dirname(importlib.util.find_spec("aqt").origin), "webview.py")
    with open(path, encoding="utf8") as f:
        tree = ast.parse(f.read())
    wanted = {"AuthInterceptor", "_is_internal_url"}
    nodes = [n for n in tree.body if getattr(n, "name", None) in wanted]
    assert {n.name for n in nodes} == wanted, "aqt.webview changed: check kioku.webengine's interceptor support"
    import aqt

    namespace = {
        "QObject": QObject,
        "QUrl": QUrl,
        "QWebEngineUrlRequestInterceptor": webengine.QWebEngineUrlRequestInterceptor,
        "QWebEngineUrlRequestInfo": webengine.QWebEngineUrlRequestInfo,
        "hmr_mode": False,
        "__name__": "aqt_webview_extract",
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, "exec"), namespace)
    fake_mw = types.SimpleNamespace(serverURL=lambda: server)
    return namespace["AuthInterceptor"], fake_mw


def test_anki_interceptor_authorizes_api_calls(monkeypatch) -> None:
    # Anki 26.09.4 only authorizes XHR POSTs to its own server, comparing the
    # request's resourceType with QWebEngineUrlRequestInfo's enum: the token
    # must still reach the pages' API calls (issue: Statistics, Deck Options,
    # the editor and the import screen answered 403 on iOS and Android)
    import aqt
    import aqt.mediasrv

    interceptor_class, fake_mw = _anki_auth_interceptor("http://127.0.0.1:40000/")
    monkeypatch.setattr(aqt, "mw", fake_mw, raising=False)
    monkeypatch.setattr(aqt.mediasrv, "_APIKEY", "secret", raising=False)
    profile = webengine.QWebEngineProfile()
    profile.setUrlRequestInterceptor(interceptor_class(api_enabled=True))
    server = QUrl("http://127.0.0.1:40000/")
    assert profile._headers_for(server, api=True) == {"Authorization": "Bearer secret"}
    assert profile._headers_for(QUrl("http://127.0.0.1:9999/"), api=True) == {}
    profile.setUrlRequestInterceptor(interceptor_class(api_enabled=False))
    assert profile._headers_for(server, api=True) == {}


def test_stand_ins_have_every_web_engine_name_anki_uses() -> None:
    # aqt imports Qt WebEngine with `from aqt.qt import *`, so a name the
    # stand-in lacks only fails when that code runs on a phone (Anki 26.09.4:
    # QWebEngineUrlRequestInfo in the request interceptor)
    import glob
    import importlib.util
    import re

    here = os.path.join(os.path.dirname(__file__), "..", "python", "PyQt6")
    provided: set[str] = set()
    for module in ("QtWebEngineCore", "QtWebEngineWidgets"):
        spec = importlib.util.spec_from_file_location(f"standin_{module}", os.path.join(here, f"{module}.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        provided |= {n for n in vars(mod) if not n.startswith("_")}
    aqt_dir = os.path.dirname(importlib.util.find_spec("aqt").origin)
    used: dict[str, str] = {}
    for path in glob.glob(os.path.join(aqt_dir, "**", "*.py"), recursive=True):
        with open(path, encoding="utf8") as f:
            for name in re.findall(r"\b(QWebEngine\w+|qWebEngine\w+)\b", f.read()):
                used.setdefault(name, os.path.relpath(path, aqt_dir))
    missing = {n: where for n, where in used.items() if n not in provided}
    assert not missing, f"used by aqt but not in kioku.webengine: {missing}"


# A WebKit-like page for SHADOW_SELECTION: document.getSelection() reports a
# selection inside a shadow root on its host, getComposedRanges() the real
# positions, addRange() ignores ranges inside the tree (issue #17)
SHADOW_PAGE = """
globalThis.window = globalThis;
const listeners = {};
function listen(name, fn) { (listeners[name] = listeners[name] || []).push(fn); }
function fire(name, event) { (listeners[name] || []).forEach(fn => fn(event)); }
globalThis.addEventListener = listen;
class ShadowRoot { constructor(host) { this.host = host; this.activeElement = null; } }
class Node {
  constructor(name, root) { this.nodeName = name; this.root = root; this.childNodes = []; }
  getRootNode() { return this.root; }
}
const doc = {};
const host = new Node("DIV", doc);
host.shadowRoot = new ShadowRoot(host);
const text = new Node("#text", host.shadowRoot);
const field = new Node("ANKI-EDITABLE", host.shadowRoot);
field.contains = n => n === text;
host.shadowRoot.activeElement = field;
class Range {
  setStart(n, o) { this.startContainer = n; this.startOffset = o; }
  setEnd(n, o) { this.endContainer = n; this.endOffset = o; }
  get collapsed() { return this.startContainer === this.endContainer && this.startOffset === this.endOffset; }
}
const real = {startContainer: text, startOffset: 0, endContainer: text, endOffset: 5, collapsed: false};
const calls = [];
class Selection {
  get rangeCount() { return globalThis.nativeCount ?? 1; }
  get anchorNode() { return host; }
  get anchorOffset() { return 0; }
  get focusNode() { return host; }
  get focusOffset() { return 0; }
  get isCollapsed() { return true; }
  getRangeAt() { const r = new Range(); r.setStart(host, 0); r.setEnd(host, 0); return r; }
  getComposedRanges(opts) { return opts.shadowRoots.includes(host.shadowRoot) ? [real] : []; }
  addRange(r) { calls.push("addRange"); }
  setBaseAndExtent(a, ao, b, bo) { calls.push(["setBaseAndExtent", a.nodeName, ao, b.nodeName, bo]); }
}
const sel = new Selection();
Object.assign(doc, {activeElement: host, getSelection: () => sel, createRange: () => new Range(),
                   addEventListener: listen});
Object.assign(globalThis, {document: doc, Selection, ShadowRoot});
%s
%s
"""

SHADOW_RANGE = """
const r = sel.getRangeAt(0);
const inner = new Range(); inner.setStart(text, 1); inner.setEnd(text, 3);
sel.addRange(inner);
sel.addRange(r === null ? null : (() => { const o = new Range(); o.setStart(host, 0); o.setEnd(host, 0); return o; })());
console.log(JSON.stringify({
  range: [r.startContainer.nodeName, r.startOffset, r.endContainer.nodeName, r.endOffset],
  anchor: [sel.anchorNode.nodeName, sel.anchorOffset], focus: [sel.focusNode.nodeName, sel.focusOffset],
  collapsed: sel.isCollapsed, calls,
}));
"""


# WebKit empties the selection before a field's blur: during the blur it
# reports where it last was in the field, and nothing once the blur is over
# or for an element it wasn't in
SHADOW_BLUR = """
const seen = [];
function look() {
  seen.push(sel.rangeCount ? [sel.rangeCount, sel.getRangeAt(0).startContainer.nodeName,
                              sel.anchorOffset, sel.focusOffset] : 0);
}
fire("selectionchange");
globalThis.nativeCount = 0;
look();
fire("blur", {composedPath: () => [field]});
look();
fire("focusout");
look();
const other = new Node("INPUT", doc);
other.contains = () => false;
fire("blur", {composedPath: () => [other]});
look();
console.log(JSON.stringify(seen));
"""


def run_shadow_page(prefix: str = "", scenario: str = SHADOW_RANGE):
    js = SHADOW_PAGE % (prefix + webscripts.SHADOW_SELECTION, scenario)
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


def test_shadow_selection_reports_the_real_range() -> None:
    assert run_shadow_page() == {
        "range": ["#text", 0, "#text", 5],
        "anchor": ["#text", 0],
        "focus": ["#text", 5],
        "collapsed": False,
        "calls": [["setBaseAndExtent", "#text", 1, "#text", 3], "addRange"],
    }


def test_shadow_selection_is_off_where_shadow_roots_have_their_own() -> None:
    # Blink: Anki uses ShadowRoot.getSelection, nothing to fix
    out = run_shadow_page("ShadowRoot.prototype.getSelection = () => null;\n")
    assert out["range"] == ["DIV", 0, "DIV", 0]
    assert out["calls"] == ["addRange", "addRange"]


def test_shadow_selection_reports_the_selection_during_blur() -> None:
    assert run_shadow_page(scenario=SHADOW_BLUR) == [0, [1, "#text", 0, 5], 0, 0]


def test_shadow_selection_script_is_installed(platform) -> None:
    page = webengine.QWebEnginePage()
    installed: list[tuple] = []
    page._web.set_user_scripts = installed.extend
    page.setHtml("<p>x</p>")
    assert (webscripts.SHADOW_SELECTION, webscripts.AT_DOCUMENT_START, True) in installed
