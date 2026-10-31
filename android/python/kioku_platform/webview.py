"""The Android web view backend: android.webkit.WebView, owned by
KiokuBridge.java and embedded into the Qt widget as a foreign window.

One WebView here wraps one Java-side page. Everything Qt-shaped (QUrl,
signals, QWebEngine* semantics) lives in kioku.webengine; this module only
speaks to KiokuBridge.
"""

from __future__ import annotations

import itertools
import json
import logging
import weakref
from typing import Any, Callable

import _kioku_android
from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QTimer
from PyQt6.QtGui import QWindow
from PyQt6.QtWidgets import QWidget

from . import bridge

logger = logging.getLogger("kioku.webview")

_ids = itertools.count(1)
_callback_ids = itertools.count(1)
_views: "weakref.WeakValueDictionary[int, WebView]" = weakref.WeakValueDictionary()


def _route(event: dict) -> None:
    view = _views.get(event.get("id", 0))
    if view is not None:
        view._event(event)


for _type in ("message", "channel", "navigate", "loadStarted", "loadFinished", "eval", "alert", "confirm", "pdf"):
    bridge.listen(_type, _route)


def _close_popups(event: dict) -> None:
    from PyQt6.QtWidgets import QApplication

    popup = QApplication.activePopupWidget()
    while popup is not None and popup.close():
        popup = QApplication.activePopupWidget()


bridge.listen("popupTap", _close_popups)


def set_cookie(url: str, header: str) -> None:
    """Store a cookie given in Set-Cookie form for url (all pages share
    android.webkit.CookieManager's jar)."""
    bridge.call("cookies.set", url=url, cookie=header)


def delete_cookies(domain: str, name: str | None) -> None:
    """Delete the cookies on domain, or only `name`."""
    bridge.call("cookies.delete", domain=domain, name=name or "")


def _main_window() -> QWidget | None:
    import aqt

    return aqt.mw


class _FollowHost(QObject):
    """Keeps the Android view over its Qt widget, but moves or shrinks it
    only once Qt has drawn what that uncovers. Qt draws nothing under the
    view, and Android placed it at once while Qt's frame came later: when
    the keyboard opened, the strip above it (the Add window's buttons)
    flashed black, and when it closed, the Browse window's editor left a
    black block where it had been. After the window's next paint,
    SHRINK_DELAY_MS more give
    the frame time to reach the screen; SHRINK_LATEST_MS is the longest
    wait. Growing covers only what the view will draw: at once."""

    SHRINK_DELAY_MS = 300
    SHRINK_LATEST_MS = 1000

    def __init__(self, host: QWidget, container: QWidget) -> None:
        super().__init__(container)
        self._host = host
        self._container = container
        self._window: QWidget | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._place)
        container.setGeometry(host.rect())
        # where the view is, in the window
        self._shown = self._host_rect()
        # the widget moves with its parents too (the Browse window's
        # splitter moves the editor's pane)
        self._chain: list[QWidget] = []
        widget: QWidget | None = host
        while widget is not None and not widget.isWindow():
            self._chain.append(widget)
            widget.installEventFilter(self)
            widget = widget.parentWidget()

    def _host_rect(self) -> QRect:
        """The widget's place in its window."""
        return QRect(self._host.mapTo(self._host.window(), QPoint(0, 0)), self._host.size())

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if event is None:
            return False
        kind = event.type()
        if kind in (QEvent.Type.Resize, QEvent.Type.Move) and obj in self._chain:
            target = self._host_rect()
            if target.contains(self._shown):
                self._place()
            else:
                # stay where it is in the window until Qt has drawn there
                self._container.setGeometry(self._shown.translated(-target.topLeft()))
                self._wait_for_paint()
        elif obj is self._window and kind == QEvent.Type.Paint:
            # the paint runs now; the frame reaches the screen after it
            self._stop_watching()
            self._timer.start(self.SHRINK_DELAY_MS)
        return False

    def _wait_for_paint(self) -> None:
        if self._window is None:
            self._window = self._host.window()
            self._window.installEventFilter(self)
            self._timer.start(self.SHRINK_LATEST_MS)

    def _stop_watching(self) -> None:
        if self._window is not None:
            self._window.removeEventFilter(self)
            self._window = None

    def _place(self) -> None:
        self._timer.stop()
        self._stop_watching()
        self._container.setGeometry(self._host.rect())
        self._shown = self._host_rect()


class WebView:
    """Callbacks (on_*) are overridden by kioku.webengine."""

    # defines window.__kiokuNative for kioku.webscripts.PRELUDE; calls are
    # answered by KiokuBridge with window.__kiokuResolve()
    BRIDGE = r"""
(function () {
    if (window.__kiokuNative) return;
    var pending = {}, next = 1, generation = kiokuAndroid.generation();
    window.__kiokuNative = {
        send: function (name, text) { kiokuAndroid.send(name, text); },
        call: function (text) {
            return new Promise(function (resolve, reject) {
                var id = next++;
                pending[id] = [resolve, reject];
                kiokuAndroid.call(id, text, generation);
            });
        }
    };
    window.__kiokuResolve = function (id, ok, value) {
        var p = pending[id];
        delete pending[id];
        if (p) (ok ? p[0] : p[1])(value);
    };
})();
"""

    @staticmethod
    def prepare_host(widget: QWidget) -> None:
        # the view follows the widget's size itself (_FollowHost)
        pass

    def __init__(self) -> None:
        self.id = next(_ids)
        self._callbacks: dict[int, Callable[[Any], None] | None] = {}
        self._container: QWidget | None = None
        self._host: QWidget | None = None
        bridge.call("webview.create", id=self.id)
        _views[self.id] = self

    # Scripts ---------------------------------------------------------------

    def set_user_scripts(self, scripts: list[tuple[str, int, bool]]) -> None:
        bridge.call(
            "webview.scripts",
            id=self.id,
            scripts=[
                {"source": source, "when": when, "mainOnly": main_only}
                for source, when, main_only in scripts
            ],
        )

    # Loading ---------------------------------------------------------------

    def load_url(self, url: str, headers: dict[str, str] | None = None) -> None:
        bridge.call("webview.load", id=self.id, url=url, headers=headers or {})

    def load_html(self, html: str, base_url: str | None) -> None:
        bridge.call("webview.html", id=self.id, html=html, base=base_url)

    def reload(self) -> None:
        bridge.call("webview.reload", id=self.id)

    def stop(self) -> None:
        bridge.call("webview.stop", id=self.id)

    def back(self) -> None:
        bridge.call("webview.back", id=self.id)

    def forward(self) -> None:
        bridge.call("webview.forward", id=self.id)

    def url(self) -> str:
        return bridge.call("webview.url", id=self.id) or ""

    def title(self) -> str:
        return bridge.call("webview.title", id=self.id) or ""

    def history(self) -> dict[str, str]:
        """URLs of the back and forward items ("" when there is none)."""
        return bridge.call("webview.history", id=self.id) or {}

    # JavaScript --------------------------------------------------------------

    def evaluate(self, js: str, callback: Callable[[Any], None] | None) -> None:
        cb = next(_callback_ids) if callback is not None else 0
        if cb:
            self._callbacks[cb] = callback
        bridge.call("webview.eval", id=self.id, js=js, cb=cb)

    def print_pdf(self, path: str) -> None:
        """Write the page to a PDF file; on_pdf_finished() reports the result."""
        bridge.call("webview.pdf", id=self.id, path=path)

    # Appearance --------------------------------------------------------------

    def set_background(self, r: float, g: float, b: float, a: float) -> None:
        argb = (round(a * 255) << 24) | (round(r * 255) << 16) | (round(g * 255) << 8) | round(b * 255)
        if argb >= 1 << 31:
            argb -= 1 << 32  # Java int
        bridge.call("webview.background", id=self.id, argb=argb)

    def set_zoom(self, factor: float) -> None:
        bridge.call("webview.zoom", id=self.id, factor=factor)

    # Hosting ---------------------------------------------------------------

    def attach(self, widget: QWidget) -> None:
        """Embed the Android view into the widget through a foreign window."""
        if self._host is widget and self._container is not None:
            return
        handle = _kioku_android.view_handle(self.id)
        if handle is None:
            return
        window = QWindow.fromWinId(handle)
        container = QWidget.createWindowContainer(window, widget)
        _FollowHost(widget, container)
        container.show()
        # kioku.windows keeps dialogs above the on-screen keyboard; the main
        # window's pages keep clear of it themselves
        bridge.call("webview.keyboardInsets", id=self.id, on=widget.window() is _main_window())
        self._container = container
        self._host = widget

    @staticmethod
    def set_touchable(on: bool) -> None:
        """Off while a Qt popup (a menu) is open: Qt doesn't see taps on the
        pages, so KiokuBridge reports them (popupTap) and the popup closes."""
        bridge.call("webview.touchable", on=on)

    def detach(self) -> None:
        if self._container is not None:
            self._container.hide()

    def close(self) -> None:
        _views.pop(self.id, None)
        bridge.call("webview.destroy", id=self.id)

    # Events from KiokuBridge -------------------------------------------------

    def _event(self, event: dict) -> None:
        kind = event["type"]
        if kind == "message":
            if event["name"] == "console":
                self.on_console(json.loads(event["text"]))
            elif event["name"] == "selection":
                self.on_selection(event["text"])
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
            if self.on_navigation(event["url"], 0, bool(event.get("main", True))):
                self.load_url(event["url"])
        elif kind == "loadStarted":
            self.on_load_started()
        elif kind == "loadFinished":
            self.on_load_finished(bool(event["ok"]))
        elif kind == "pdf":
            self.on_pdf_finished(event["path"], bool(event["ok"]))
        elif kind == "alert":
            self.on_alert(event["text"])
        elif kind == "confirm":
            ok = False
            try:
                ok = bool(self.on_confirm(event["text"]))
            finally:
                bridge.call("webview.confirmResult", id=self.id, token=event["token"], ok=ok)

    def _channel(self, event: dict) -> None:
        if event.get("stale"):
            # from the previous document: Anki would take its "domDone" for
            # the page now loading and run queued JavaScript on the old one
            bridge.call("webview.reply", id=self.id, call=event["call"], ok=True, value="null")
            return
        try:
            call = json.loads(event["text"])
            result = self.on_channel_call(call["obj"], call["method"], call.get("args", []))
            ok, value = True, json.dumps(result)
        except Exception as e:
            logger.exception("channel call failed")
            ok, value = False, str(e)
        bridge.call("webview.reply", id=self.id, call=event["call"], ok=ok, value=value)

    # Callbacks, overridden by the owner -------------------------------------

    def on_console(self, entry: dict) -> None: ...
    def on_selection(self, text: str) -> None: ...
    def on_channel_call(self, obj: str, method: str, args: list) -> Any: ...
    def on_navigation(self, url: str, nav_type: int, main_frame: bool) -> bool:
        return True
    def on_load_started(self) -> None: ...
    def on_load_finished(self, ok: bool) -> None: ...
    def on_alert(self, text: str) -> None: ...
    def on_pdf_finished(self, path: str, ok: bool) -> None: ...
    def on_confirm(self, text: str) -> bool:
        return False
