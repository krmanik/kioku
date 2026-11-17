"""Anki's main window and main view have a minimum width of 400 px, wider
than phones with a 360 px screen: the main window was wider than the
screen and its pages were cut off on the right (GitHub issue #14,
kioku.patches)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import aqt.main
from aqt.qt import QApplication, QMainWindow, QSize, QVBoxLayout, QWidget

from kioku import patches

app = QApplication.instance() or QApplication([])


class MainWindow(QMainWindow):
    """Stands in for aqt.main.AnkiQt, its setupMainWindow() sizes as Anki's."""

    def setupMainWindow(self) -> None:
        self.setMinimumSize(QSize(400, 0))  # the main.ui form
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        self.web = QWidget()
        self.web.setMinimumWidth(400)  # MainWebView
        layout.addWidget(self.web)
        self.setCentralWidget(central)


def test_main_window_fits_a_narrow_screen(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(aqt.main, "AnkiQt", MainWindow)
    monkeypatch.setattr(MainWindow, "setupMainWindow", MainWindow.setupMainWindow)
    patches._patch_main_view_width()

    window = MainWindow()
    window.setupMainWindow()
    try:
        assert window.minimumWidth() == 0
        assert window.web.minimumWidth() == 0
        window.resize(360, 700)
        window.show()
        app.processEvents()
        assert window.width() == 360
        assert window.web.width() == 360
    finally:
        window.close()
