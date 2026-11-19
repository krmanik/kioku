"""Platform code that cannot run on the host as is: the iOS layer needs the
Objective-C runtime and the web layer a native module. Both are replaced
at their outer edge (rubicon, _kioku_web); the Kioku code runs as shipped."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import types
from unittest.mock import MagicMock

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")


class Stub(types.ModuleType):
    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        if name.startswith("__"):
            raise AttributeError(name)
        return MagicMock()


def load_package(monkeypatch, src: str, name: str, copy_to: str | None = None):  # type: ignore[no-untyped-def]
    if copy_to:
        shutil.copytree(src, copy_to)
        src = copy_to
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(src, "__init__.py"), submodule_search_locations=[src]
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ios(monkeypatch, tmp_path):  # type: ignore[no-untyped-def]
    objc = Stub("rubicon.objc")
    objc.NSObject = type(
        "NSObject", (), {"alloc": classmethod(lambda cls: cls()), "init": lambda self: self}
    )
    objc.objc_method = lambda f: f
    for name, mod in {
        "rubicon": Stub("rubicon"),
        "rubicon.objc": objc,
        "rubicon.objc.api": Stub("rubicon.objc.api"),
        "rubicon.objc.runtime": Stub("rubicon.objc.runtime"),
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)
    # <app>/app/kioku_platform/__init__.py, as bundle_python.sh lays it out
    package = load_package(
        monkeypatch,
        os.path.join(ROOT, "ios", "python", "kioku_platform"),
        "ios_kioku_platform",
        str(tmp_path / "App.app" / "app" / "kioku_platform"),
    )
    package.app_dir = str(tmp_path / "App.app")
    return package


class Message:
    def __init__(self, main_frame: bool, body: str = "{}") -> None:
        self.frameInfo = types.SimpleNamespace(isMainFrame=main_frame)
        self.body = body
        self.name = "kiokuChannel"


def test_ios_dev_allowed_needs_the_marker_in_the_app(ios, monkeypatch) -> None:
    monkeypatch.delenv("KIOKU_DEV", raising=False)
    assert ios.dev_allowed() is False
    open(os.path.join(ios.app_dir, "dev-build"), "w").close()
    assert ios.dev_allowed() is True
    os.remove(os.path.join(ios.app_dir, "dev-build"))
    monkeypatch.setenv("KIOKU_DEV", "1")
    assert ios.dev_allowed() is True


def test_ios_channel_call_from_a_sub_frame_never_reaches_the_view(ios, monkeypatch) -> None:
    webview = sys.modules["ios_kioku_platform.webview"]
    calls: list = []
    replies: list = []

    class View:
        def on_channel_call(self, *args):  # type: ignore[no-untyped-def]
            calls.append(args)
            return "ok"

    monkeypatch.setattr(webview, "_view_for_controller", lambda controller: View())
    monkeypatch.setattr(webview, "prop", lambda obj, name: getattr(obj, name))
    monkeypatch.setattr(webview, "at", lambda value: value)
    monkeypatch.setattr(
        webview, "block", lambda ptr, *types: lambda *args: replies.append(args)
    )
    handler = webview.KiokuScriptHandler()
    body = '{"obj": "py", "method": "cmd", "args": ["x"]}'
    handler.userContentController_didReceiveScriptMessage_replyHandler_(
        None, Message(False, body), None
    )
    assert calls == []
    assert replies == [(None, "the web channel is for the main frame")]
    handler.userContentController_didReceiveScriptMessage_replyHandler_(
        None, Message(True, body), None
    )
    assert calls == [("py", "cmd", ["x"])]
    assert replies[-1] == ('"ok"', None)


def test_ios_sub_frame_console_and_selection_messages_are_dropped(ios, monkeypatch) -> None:
    webview = sys.modules["ios_kioku_platform.webview"]
    seen: list = []

    class View:
        def on_selection(self, text):  # type: ignore[no-untyped-def]
            seen.append(text)

        def on_console(self, entry):  # type: ignore[no-untyped-def]
            seen.append(entry)

    monkeypatch.setattr(webview, "_view_for_controller", lambda controller: View())
    monkeypatch.setattr(webview, "prop", lambda obj, name: getattr(obj, name))
    handler = webview.KiokuScriptHandler()
    for main_frame in (False, True):
        for name, body in ((webview.SELECTION_HANDLER, "text"), (webview.CONSOLE_HANDLER, '"log"')):
            message = Message(main_frame, body)
            message.name = name
            handler.userContentController_didReceiveScriptMessage_(None, message)
    assert seen == ["text", "log"]


def test_web_server_origin_is_the_page_origin(monkeypatch) -> None:
    # the auth script matches _origin(mw.serverURL()); on web that has to be
    # the origin the browser loads pages from
    from PyQt6.QtCore import QUrl
    import aqt.main
    import aqt.mediasrv
    import aqt.webview
    from kioku import webengine

    for cls, attr in (
        (aqt.mediasrv.MediaServer, "run"),
        (aqt.mediasrv.MediaServer, "getPort"),
        (aqt.mediasrv.MediaServer, "shutdown"),
        (aqt.main.AnkiQt, "serverURL"),
        (aqt.webview.AnkiWebView, "webBundlePath"),
    ):
        monkeypatch.setattr(cls, attr, getattr(cls, attr))  # restored afterwards
    monkeypatch.setitem(sys.modules, "_kioku_web", Stub("_kioku_web"))
    spec = importlib.util.spec_from_file_location(
        "web_http", os.path.join(ROOT, "web", "python", "kioku_platform", "http.py")
    )
    http = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(http)
    for page_origin in ("http://localhost:8000", "http://[::1]:8000", "https://kioku.example"):
        http.setup(page_origin)
        server_url = aqt.main.AnkiQt.serverURL(None)
        assert webengine._origin(QUrl(server_url)) == page_origin


def test_ios_menu_bar_rows_and_key_commands(ios) -> None:
    """Anki's menus in the iPadOS menu bar: which shortcuts become UIKit key
    commands (Cmd/Ctrl/Option ones; single keys stay with Qt, they would take
    letters from text fields) and how rows are titled."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QAction, QKeySequence
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])  # noqa: F841
    menubar = importlib.import_module("ios_kioku_platform.menubar")

    def command(shortcut: str, context=None):  # type: ignore[no-untyped-def]
        action = QAction("x")
        action.setShortcut(QKeySequence(shortcut))
        if context is not None:
            action.setShortcutContext(context)
        return menubar._key_command(action)

    # Qt's Ctrl is Command on Apple platforms, Meta is Control
    assert command("Ctrl+Z") == ("z", menubar.COMMAND)
    assert command("Ctrl+Shift+Z") == ("z", menubar.COMMAND | menubar.SHIFT)
    assert command("Ctrl+Alt+F") == ("f", menubar.COMMAND | menubar.OPTION)
    assert command("Meta+1") == ("1", menubar.CONTROL)
    assert command("Ctrl+0") == ("0", menubar.COMMAND)
    assert command("D") is None
    assert command("Shift+V") is None
    assert command("/") is None
    assert command("") is None
    # the review menu's rows are inert (patches._patch_review_menu)
    assert command("Ctrl+1", Qt.ShortcutContext.WidgetShortcut) is None

    assert menubar._plain("&File") == "File"
    assert menubar._plain("Save && Close") == "Save & Close"
    assert menubar._plain("&Undo\tCtrl+Z") == "Undo"


class FakeLocationManager:
    def __init__(self) -> None:
        self.authorizationStatus = 0  # not determined
        self.calls: list[tuple] = []
        self.ptr = types.SimpleNamespace(value=id(self))

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args: self.calls.append((name, *args))


def test_ios_keep_running_asks_then_starts_and_stops(ios, monkeypatch) -> None:
    import importlib

    location = importlib.import_module("ios_kioku_platform.location")
    manager = FakeLocationManager()
    cls = MagicMock()
    cls.alloc.return_value.init.return_value = manager
    monkeypatch.setattr(location, "ObjCClass", lambda name: cls)
    monkeypatch.setattr(location, "prop", lambda obj, name: getattr(obj, name))
    monkeypatch.setattr(location, "_manager", None)
    names = lambda: [c[0] for c in manager.calls]  # noqa: E731

    ios.keep_running_in_background(False)
    assert location._manager is None  # off: nothing created, nothing asked
    ios.keep_running_in_background(True)
    assert "requestWhenInUseAuthorization" in names()
    assert "startUpdatingLocation" not in names()
    assert ios.keep_running_in_background_status() == "asking"

    manager.authorizationStatus = 4  # when in use: iOS calls the delegate
    location._delegate.locationManagerDidChangeAuthorization_(manager)
    assert ("setAllowsBackgroundLocationUpdates_", True) in manager.calls
    assert ("setPausesLocationUpdatesAutomatically_", False) in manager.calls
    assert names()[-1] == "startUpdatingLocation"
    assert ios.keep_running_in_background_status() == "on"

    ios.keep_running_in_background(False)
    assert manager.calls[-2:] == [("stopUpdatingLocation",), ("setAllowsBackgroundLocationUpdates_", False)]
    assert ios.keep_running_in_background_status() == "allowed"  # take it back in Settings

    manager.authorizationStatus = 2  # denied in the Settings app
    ios.keep_running_in_background(True)
    assert ios.keep_running_in_background_status() == "denied"
    assert names()[-1] == "setAllowsBackgroundLocationUpdates_"


def test_ios_location_guard_only_kiokus_manager(ios, monkeypatch) -> None:
    import importlib

    location = importlib.import_module("ios_kioku_platform.location")
    ours = types.SimpleNamespace(ptr=types.SimpleNamespace(value=1000))
    delegate = types.SimpleNamespace(ptr=types.SimpleNamespace(value=2000))
    monkeypatch.setattr(location, "_manager", ours)
    monkeypatch.setattr(location, "_delegate", delegate)
    for name in ("requestWhenInUseAuthorization", "startUpdatingLocation", "requestLocation"):
        assert location.allowed(1000, name)
        assert not location.allowed(3000, name)  # an add-on's or WebKit's manager
    assert not location.allowed(1000, "requestTemporaryFullAccuracyAuthorizationWithPurposeKey:", (5,))
    assert location.allowed(1000, "setDelegate:", (2000,))
    assert not location.allowed(1000, "setDelegate:", (4000,))  # someone else's delegate on ours
    assert location.allowed(3000, "setDelegate:", (4000,))  # theirs never gets locations
    monkeypatch.setattr(location, "_manager", None)
    assert not location.allowed(1000, "startUpdatingLocation")
    assert not location.allowed(None, "startUpdatingLocation")
    assert set(location.GUARDED) >= {
        "requestWhenInUseAuthorization", "requestAlwaysAuthorization", "startUpdatingLocation",
        "requestLocation", "startMonitoringSignificantLocationChanges", "startMonitoringVisits",
    }
