"""kioku.screenedges: Anki's web views reach the screen's edges, their pages
padded by the safe area; while Anki hides the bottom bar (shrinks it to
1 px), the window keeps out of the bottom safe area."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QMargins
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget

from kioku.screenedges import STYLE_ID, ScreenEdges
from kioku.webengine import QWebEngineScriptCollection

app = QApplication.instance() or QApplication([])

PORTRAIT = QMargins(0, 59, 0, 34)
LANDSCAPE = QMargins(59, 0, 59, 20)


class Handle:
    def __init__(self) -> None:
        self.margins = PORTRAIT

    def safeAreaMargins(self) -> QMargins:
        return self.margins


class Page:
    def __init__(self) -> None:
        self._scripts = QWebEngineScriptCollection()

    def scripts(self) -> QWebEngineScriptCollection:
        return self._scripts


class Web(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.hidden = False
        self.heads: list[str] = []
        self.scripts: list[str] = []
        self.adjusted = 0
        self._page = Page()

    def page(self) -> Page:
        return self._page

    def stdHtml(self, body: str, css=None, js=None, head: str = "", context=None) -> None:  # type: ignore[no-untyped-def]
        self.heads.append(head)

    def eval(self, js: str) -> None:
        self.scripts.append(js)

    def adjustHeightToFit(self) -> None:
        self.adjusted += 1


class Main(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.handle = Handle()
        self.toolbarWeb = Web(self)
        self.web = Web(self)
        self.bottomWeb = Web(self)

    def windowHandle(self):  # type: ignore[no-untyped-def]
        return self.handle


def margins(w: QWidget) -> tuple[int, int, int, int]:
    m = w.contentsMargins()
    return (m.left(), m.top(), m.right(), m.bottom())


def test_views_take_the_safe_area() -> None:
    mw = Main()
    edges = ScreenEdges(mw)
    assert margins(mw) == (0, 59, 0, 0)
    assert edges.bottom.insets == {"bottom": 34} and edges.main.insets == {}
    assert mw.bottomWeb.adjusted == 1 and "'34px'" in mw.bottomWeb.scripts[-1]
    # Anki's pages, head passed by keyword or position, get the padding
    mw.bottomWeb.stdHtml("<p>", css=["a.css"], context=None)
    mw.bottomWeb.stdHtml("<p>", ["a.css"], [], "<style>x</style>")
    assert all("padding-bottom: var(--kioku-safe-bottom, 34px)" in h for h in mw.bottomWeb.heads)
    assert mw.bottomWeb.heads[1].startswith("<style>x</style>")
    # pages not made with stdHtml get it from a page script
    assert [s.name() for s in mw.bottomWeb.page().scripts().toList()] == [STYLE_ID]


def test_rotation_moves_the_padding_to_the_sides() -> None:
    mw = Main()
    edges = ScreenEdges(mw)
    mw.handle.margins = LANDSCAPE
    edges.update()
    assert margins(mw) == (0, 0, 0, 0)
    first = mw.menuBar().addMenu("File")
    mw.show()
    assert [w.width() for w in edges.corners.values()] == [59, 59]
    assert mw.menuBar().actionGeometry(first.menuAction()).left() >= 59
    assert edges.top.insets == edges.main.insets == {"left": 59, "right": 59}
    assert edges.bottom.insets == {"left": 59, "right": 59, "bottom": 20}
    mw.web.stdHtml("<p>")
    assert "padding-left: var(--kioku-safe-left, 59px)" in mw.web.heads[-1]
    assert len(mw.web.page().scripts().toList()) == 1  # replaced, not added
    mw.handle.margins = PORTRAIT
    edges.update()
    assert edges.main.insets == {} and "'0px'" in mw.web.scripts[-1]


def test_hidden_bar_leaves_the_bottom_safe_area_alone() -> None:
    mw = Main()
    edges = ScreenEdges(mw)
    mw.bottomWeb.hidden = True  # Anki's BottomWebView.hide()
    edges.update()
    assert margins(mw) == (0, 59, 0, 34) and edges.bottom.insets == {}
    mw.bottomWeb.hidden = False
    edges.update()
    assert margins(mw) == (0, 59, 0, 0) and edges.bottom.insets == {"bottom": 34}


def test_keyboard_keeps_the_bottom_bar_above_it(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Android: the main window keeps its size while the keyboard is open
    (windows._fill_main), so Android 11 to 14 left the reviewer's bottom bar
    (Show Answer) under the keyboard. The window keeps out of the part the
    keyboard covers; the bar drops its gesture bar padding meanwhile."""
    from kioku import screenedges

    overlap = {"px": 0}
    monkeypatch.setattr(screenedges.windows, "keyboard_overlap", lambda w: overlap["px"])
    mw = Main()
    edges = ScreenEdges(mw)
    adjusted = mw.bottomWeb.adjusted
    overlap["px"] = 300
    edges.update()
    assert margins(mw) == (0, 59, 0, 300) and edges.bottom.insets == {}
    assert mw.bottomWeb.adjusted == adjusted + 1  # bar shrinks to its buttons
    overlap["px"] = 0
    edges.update()
    assert margins(mw) == (0, 59, 0, 0) and edges.bottom.insets == {"bottom": 34}
