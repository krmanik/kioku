"""kioku.windows: add-on windows can drop the title bar (kioku_hide_titlebar)
and reach the screen's edges (kioku_edge_to_edge), padding their contents by
safe_area() or the --kioku-safe-* CSS properties; windows fill the screen
before they are first drawn; add-ons can hide Anki's menu row
(kioku_hide_menu_row). GitHub issues #32 and #33."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import types

import pytest
from aqt.qt import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMainWindow,
    QMargins,
    QMenuBar,
    QObject,
    QRect,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)

from kioku import windows
from kioku.webengine import QWebEngineScriptCollection

app = QApplication.instance() or QApplication([])

SCREEN = QRect(0, 0, 402, 874)
PORTRAIT = QMargins(0, 62, 0, 34)
LANDSCAPE = QMargins(62, 0, 62, 21)


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    safe = {"margins": PORTRAIT}
    monkeypatch.setattr(windows.sys, "platform", "ios")
    monkeypatch.setattr(windows, "_available", lambda: QRect(SCREEN))
    monkeypatch.setattr(windows, "_safe_area", lambda w: QMargins(safe["margins"]))
    m = windows.WindowManager(app)
    m.safe = safe  # type: ignore[attr-defined]
    yield m
    app.removeEventFilter(m)
    for w in QApplication.topLevelWidgets():
        w.close()
    m.deleteLater()


class Page(QObject):
    loadFinished = pyqtSignal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._scripts = QWebEngineScriptCollection()
        self.ran: list[str] = []

    def scripts(self) -> QWebEngineScriptCollection:
        return self._scripts

    def runJavaScript(self, js: str) -> None:
        self.ran.append(js)


class QWebEngineView(QWidget):
    """Found by its class name, like Kioku's stand-in and Qt's own."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._page = Page()

    def page(self) -> Page:
        return self._page


def margins(w: QWidget) -> tuple[int, int, int, int]:
    m = w.contentsMargins()
    return (m.left(), m.top(), m.right(), m.bottom())


def window(**options: bool) -> QDialog:
    w = QDialog()
    QVBoxLayout(w).addWidget(QLabel("statistics"))
    w.layout().setContentsMargins(0, 0, 0, 0)
    w.setContentsMargins(0, 0, 0, 0)
    for name, value in options.items():
        w.setProperty(name, value)
    return w


def shown(w: QWidget) -> QWidget:
    w.show()
    app.processEvents()
    return w


def bar(w: QWidget) -> windows.TitleBar | None:
    return windows.WindowManager._bar(w)


def test_windows_keep_the_title_bar_and_safe_area(manager) -> None:  # type: ignore[no-untyped-def]
    w = shown(window())
    assert bar(w) is not None and not bar(w).isHidden()
    assert margins(w) == (0, 62 + windows.BAR_HEIGHT, 0, 34)
    assert windows.safe_area(w) == QMargins()


def test_hide_title_bar(manager) -> None:  # type: ignore[no-untyped-def]
    w = shown(window(kioku_hide_titlebar=True))
    assert bar(w) is None
    # the status bar's room stays: no 44 px gap where the bar was
    assert margins(w) == (0, 62, 0, 34)
    assert w.size() == SCREEN.size()  # offscreen adds a frame offset


def test_edge_to_edge(manager) -> None:  # type: ignore[no-untyped-def]
    w = shown(window(kioku_hide_titlebar=True, kioku_edge_to_edge=True))
    assert margins(w) == (0, 0, 0, 0)
    assert windows.safe_area(w) == PORTRAIT


def test_edge_to_edge_landscape_sides(manager) -> None:  # type: ignore[no-untyped-def]
    manager.safe["margins"] = LANDSCAPE
    w = shown(window(kioku_hide_titlebar=True, kioku_edge_to_edge=True))
    assert margins(w) == (0, 0, 0, 0)
    assert windows.safe_area(w) == LANDSCAPE


def test_edge_to_edge_under_the_title_bar(manager) -> None:  # type: ignore[no-untyped-def]
    w = shown(window(kioku_edge_to_edge=True))
    assert margins(w) == (0, 62 + windows.BAR_HEIGHT, 0, 0)
    assert windows.safe_area(w) == QMargins(0, 0, 0, 34)


def test_own_margins_are_kept(manager) -> None:  # type: ignore[no-untyped-def]
    w = window(kioku_hide_titlebar=True, kioku_edge_to_edge=True)
    w.setContentsMargins(5, 6, 7, 8)
    shown(w)
    assert margins(w) == (5, 6, 7, 8)
    assert windows.safe_area(w) == PORTRAIT


def test_title_bar_clear_of_the_notch(manager) -> None:  # type: ignore[no-untyped-def]
    manager.safe["margins"] = LANDSCAPE
    w = shown(window())
    m = bar(w).layout().contentsMargins()
    assert (m.left(), m.right()) == (8 + 62, 8 + 62)
    assert margins(w) == (62, windows.BAR_HEIGHT, 62, 21)


def test_options_set_after_show(manager) -> None:  # type: ignore[no-untyped-def]
    w = shown(window())
    w.setProperty("kioku_hide_titlebar", True)
    w.setProperty("kioku_edge_to_edge", True)
    assert bar(w).isHidden()
    assert margins(w) == (0, 0, 0, 0)
    w.setProperty("kioku_hide_titlebar", False)
    w.setProperty("kioku_edge_to_edge", None)
    assert not bar(w).isHidden()
    assert margins(w) == (0, 62 + windows.BAR_HEIGHT, 0, 34)


def test_small_dialog_that_opts_in_fills_the_screen(manager) -> None:  # type: ignore[no-untyped-def]
    w = window(kioku_hide_titlebar=True)
    w.layout().addWidget(QDialogButtonBox(QDialogButtonBox.StandardButton.Ok))
    assert windows._is_small_dialog(w, SCREEN)
    shown(w)
    assert w.size() == SCREEN.size()  # offscreen adds a frame offset
    assert manager._border(w) is None


def test_web_views_get_the_safe_area(manager) -> None:  # type: ignore[no-untyped-def]
    w = window(kioku_hide_titlebar=True, kioku_edge_to_edge=True)
    web = QWebEngineView(w)
    w.layout().addWidget(web)
    shown(w)
    scripts = web.page().scripts().find(windows.SAFE_AREA_SCRIPT)
    assert len(scripts) == 1
    js = scripts[0].sourceCode()
    for side, value in (("top", 62), ("right", 0), ("bottom", 34), ("left", 0)):
        assert f"'--kioku-safe-{side}','{value}px'" in js
    assert web.page().ran[-1] == js
    # a page that was loading gets them when it has loaded
    web.page().ran.clear()
    web.page().loadFinished.emit(True)
    assert web.page().ran == [js]
    # a rotation replaces it
    manager.safe["margins"] = LANDSCAPE
    manager._layout(w)
    scripts = web.page().scripts().find(windows.SAFE_AREA_SCRIPT)
    assert len(scripts) == 1 and "'--kioku-safe-left','62px'" in scripts[0].sourceCode()
    # no longer edge to edge: Kioku keeps the margins, the page none
    w.setProperty("kioku_edge_to_edge", False)
    js = web.page().scripts().find(windows.SAFE_AREA_SCRIPT)[0].sourceCode()
    assert "'--kioku-safe-left','0px'" in js and "'--kioku-safe-bottom','0px'" in js


def test_web_view_shown_later(manager) -> None:  # type: ignore[no-untyped-def]
    w = shown(window(kioku_hide_titlebar=True, kioku_edge_to_edge=True))
    web = QWebEngineView(w)
    w.layout().addWidget(web)
    web.show()
    assert web.page().scripts().find(windows.SAFE_AREA_SCRIPT)


def test_other_windows_web_views_are_left_alone(manager) -> None:  # type: ignore[no-untyped-def]
    w = window()
    web = QWebEngineView(w)
    w.layout().addWidget(web)
    shown(w)
    assert not web.page().scripts().find(windows.SAFE_AREA_SCRIPT)


def test_filled_before_first_drawn(manager) -> None:  # type: ignore[no-untyped-def]
    # issue #33: no event loop turn between show() and the full size
    w = window()
    w.resize(300, 200)
    w.show()
    assert w.size() == SCREEN.size()  # offscreen adds a frame offset
    assert bar(w) is not None


def test_message_boxes_wait_for_their_size(manager) -> None:  # type: ignore[no-untyped-def]
    from aqt.qt import QMessageBox

    box = QMessageBox()
    box.setText("Sync conflict")
    box.show()
    assert box.property(windows.OWN_MARGINS) is None
    app.processEvents()
    assert manager._border(box) is not None
    assert box.size() != SCREEN.size()


# --- menu row ---------------------------------------------------------------


class Hooks(list):
    def append(self, fn) -> None:  # type: ignore[no-untyped-def,override]
        super().append(fn)


class Main(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.form = types.SimpleNamespace(menubar=QMenuBar(self))
        self.fullscreen = False

    def show_menubar(self) -> None:
        import aqt.main

        aqt.main.AnkiQt.show_menubar(self)

    def hide_menubar(self) -> None:
        import aqt.main

        aqt.main.AnkiQt.hide_menubar(self)


@pytest.fixture
def main(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    import aqt
    import aqt.main
    from aqt import gui_hooks

    from kioku import patches

    monkeypatch.setattr(aqt.main.AnkiQt, "show_menubar", aqt.main.AnkiQt.show_menubar)
    hooks = Hooks()
    monkeypatch.setattr(gui_hooks, "main_window_did_init", hooks)
    mw = Main()
    monkeypatch.setattr(aqt, "mw", mw, raising=False)
    patches._patch_menu_row_property()
    for hook in hooks:
        hook()
    yield mw
    mw.close()


def row_height(mw: Main) -> int:
    return mw.form.menubar.maximumHeight()


def test_menu_row_hidden_by_property(main) -> None:  # type: ignore[no-untyped-def]
    main.setProperty("kioku_hide_menu_row", True)
    assert row_height(main) == 0
    main.setProperty("kioku_hide_menu_row", False)
    assert row_height(main) > 0


def test_menu_row_stays_hidden_after_full_screen(main) -> None:  # type: ignore[no-untyped-def]
    main.setProperty("kioku_hide_menu_row", True)
    main.hide_menubar()
    main.show_menubar()  # what leaving full screen does
    assert row_height(main) == 0


def test_menu_row_given_back_stays_hidden_in_full_screen(main) -> None:  # type: ignore[no-untyped-def]
    main.setProperty("kioku_hide_menu_row", True)
    main.fullscreen = True
    main.setProperty("kioku_hide_menu_row", None)
    assert row_height(main) == 0


def test_set_before_show_publishes_the_expected_area(manager, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import aqt

    class Handle:
        def safeAreaMargins(self) -> QMargins:
            return QMargins(PORTRAIT)

    mw = types.SimpleNamespace(windowHandle=lambda: Handle())
    monkeypatch.setattr(windows.sip, "isdeleted", lambda o: False)
    monkeypatch.setattr(aqt, "mw", mw, raising=False)
    w = window()
    web = QWebEngineView(w)
    w.setProperty("kioku_hide_titlebar", True)
    w.setProperty("kioku_edge_to_edge", True)
    js = web.page().scripts().find(windows.SAFE_AREA_SCRIPT)[0].sourceCode()
    assert "'--kioku-safe-top','62px'" in js and "'--kioku-safe-bottom','34px'" in js

