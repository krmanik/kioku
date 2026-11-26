"""kioku.safemode: Anki without add-ons after a start that didn't finish, from
the app icon's quick action, or ?safe=1 on the web (GitHub issue #32)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import plistlib
import types

import pytest

from kioku import safemode

PLIST = os.path.join(os.path.dirname(__file__), "..", "..", "ios", "src", "Info.plist.in")
SHORTCUTS = os.path.join(os.path.dirname(__file__), "..", "..", "android", "package", "res", "xml", "shortcuts.xml")


class Hooks(list):
    pass


@pytest.fixture
def start(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """begin() in a fresh Documents folder; returns a function that runs
    the patched AnkiQt.__init__ and gives the opts it passed on."""
    import aqt.main
    from aqt import gui_hooks

    monkeypatch.delenv("KIOKU_SAFE_MODE", raising=False)
    monkeypatch.setattr(aqt.main.AnkiQt, "__init__", lambda self, *a: setattr(self, "args", a))
    for name in ("main_window_did_init", "profile_did_open", "deck_browser_will_render_content",
                 "webview_did_receive_js_message"):
        monkeypatch.setattr(gui_hooks, name, Hooks())
    addons = tmp_path / "addons21"
    addons.mkdir()
    pm = types.SimpleNamespace(addonFolder=lambda: str(addons))

    monkeypatch.setattr(safemode.sys, "argv", ["kioku"])

    def run(**opts):  # type: ignore[no-untyped-def]
        safemode.begin(str(tmp_path))
        o = types.SimpleNamespace(safemode=False, **opts)
        # like AnkiApp: from the arguments
        app = types.SimpleNamespace(safeMode="--safemode" in safemode.sys.argv)
        mw = types.SimpleNamespace()
        aqt.main.AnkiQt.__init__(mw, app, pm, None, o, [])
        # what the main window takes
        o.safemode = app.safeMode
        return o

    run.docs = tmp_path  # type: ignore[attr-defined]
    run.addons = addons  # type: ignore[attr-defined]
    return run


def test_a_normal_start_is_not_safe_mode(start) -> None:  # type: ignore[no-untyped-def]
    from aqt import gui_hooks

    assert not start().safemode
    # the profile opens inside the main window's __init__: the hook that
    # clears the marker must be there before it
    assert safemode._profile_opened in gui_hooks.profile_did_open
    assert (start.docs / safemode.STARTING).exists()
    safemode.finished()
    assert not (start.docs / safemode.STARTING).exists()


def test_quick_action_request_is_taken(start) -> None:  # type: ignore[no-untyped-def]
    (start.docs / safemode.REQUEST).write_text("")
    assert start().safemode
    assert not (start.docs / safemode.REQUEST).exists()
    # only once
    safemode.finished()
    safemode.sys.argv.remove("--safemode")
    assert not start().safemode


def test_environment(start, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from aqt import gui_hooks

    monkeypatch.setenv("KIOKU_SAFE_MODE", "1")
    assert start().safemode
    # the banner is in place before the first deck list
    assert safemode._banner in gui_hooks.deck_browser_will_render_content


def test_platform_request(start, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import kioku_platform

    monkeypatch.setattr(kioku_platform, "safe_mode_requested", lambda: True, raising=False)
    assert start().safemode


def test_unfinished_start_asks_when_there_are_addons(start, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    asked = []
    monkeypatch.setattr(safemode, "_ask_after_crash", lambda: asked.append(1) or True)
    (start.docs / safemode.STARTING).write_text("")
    (start.addons / "1234567").mkdir()
    assert start().safemode
    assert asked == [1]


def test_unfinished_start_without_addons_doesnt_ask(start, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(safemode, "_ask_after_crash", lambda: pytest.fail("asked"))
    (start.docs / safemode.STARTING).write_text("")
    (start.addons / ".hidden").mkdir()
    assert not start().safemode


def test_start_normally_after_unfinished_start(start, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(safemode, "_ask_after_crash", lambda: False)
    (start.docs / safemode.STARTING).write_text("")
    (start.addons / "1234567").mkdir()
    assert not start().safemode


def test_no_start_marker_on_the_web(start, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(safemode.sys, "platform", "emscripten")
    start()
    assert not (start.docs / safemode.STARTING).exists()


def test_previous_log_is_kept(tmp_path) -> None:  # type: ignore[no-untyped-def]
    log = tmp_path / "kioku.log"
    log.write_text("last start")
    safemode.keep_previous_log(str(tmp_path), str(log))
    assert log.exists()  # a start that finished: nothing to keep
    (tmp_path / safemode.STARTING).write_text("")
    safemode.keep_previous_log(str(tmp_path), str(log))
    assert (tmp_path / safemode.PREVIOUS_LOG).read_text() == "last start"


def test_banner_on_the_deck_list() -> None:
    content = types.SimpleNamespace(tree="<table></table>")
    safemode._banner(None, content)
    assert content.tree.startswith(safemode.BANNER) and safemode.COMMAND in content.tree


def test_banner_command_is_handled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from aqt.qt import QTimer

    monkeypatch.setattr(QTimer, "singleShot", lambda *a: None)
    assert safemode._on_js_message((False, None), safemode.COMMAND, None) == (True, None)
    assert safemode._on_js_message((False, None), "other", None) == (False, None)


def test_ios_quick_action() -> None:
    with open(PLIST, "rb") as f:
        plist = plistlib.load(f)
    items = {i["UIApplicationShortcutItemType"]: i for i in plist["UIApplicationShortcutItems"]}
    assert "io.ankidesk.kioku.safe-mode" in items


def test_android_shortcut() -> None:
    with open(SHORTCUTS, encoding="utf8") as f:
        xml = f.read()
    assert 'android:action="io.ankidesk.kioku.SAFE_MODE"' in xml
    java = os.path.join(os.path.dirname(SHORTCUTS), "..", "..", "src", "io", "ankidesk", "kioku", "KiokuActivity.java")
    with open(java, encoding="utf8") as f:
        assert '"io.ankidesk.kioku.SAFE_MODE"' in f.read()
    assert safemode.REQUEST == ".kioku-safe-mode"
