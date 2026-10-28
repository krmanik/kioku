"""kioku.maindocks: a reader docked beside Anki's main view, as the
Incremento add-on docks one (550 px wide, on the right)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import aqt
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDockWidget, QMainWindow, QWidget

from kioku.maindocks import MainDocks

app = QApplication.instance() or QApplication([])

RIGHT = Qt.DockWidgetArea.RightDockWidgetArea
BOTTOM = Qt.DockWidgetArea.BottomDockWidgetArea


def make(width: int) -> tuple[QMainWindow, MainDocks, QDockWidget]:
    window = QMainWindow()
    window.setCentralWidget(QWidget())
    window.setFixedSize(width, 800)
    window.show()
    docks = MainDocks(window)
    dock = QDockWidget("Reader")
    dock.setWidget(QWidget())
    dock.setMinimumWidth(550)
    window.addDockWidget(docks.added(dock, RIGHT), dock)
    settle()
    return window, docks, dock


def settle() -> None:
    # past MainDocks' 200 ms wait for resizes to end
    QTest.qWait(300)


def test_phone_stacks_the_dock() -> None:
    window, _, dock = make(390)
    assert window.dockWidgetArea(dock) == BOTTOM
    assert dock.minimumWidth() == 0
    assert dock.geometry().right() < window.width()
    # the main view keeps about half the height
    assert abs(window.centralWidget().height() - dock.height()) < 120


def test_tablet_keeps_the_side() -> None:
    window, _, dock = make(1024)
    assert window.dockWidgetArea(dock) == RIGHT
    assert dock.minimumWidth() == 1024 // 3


def test_rotation_moves_the_dock() -> None:
    window, _, dock = make(390)
    window.setFixedSize(900, 400)
    settle()
    assert window.dockWidgetArea(dock) == RIGHT
    window.setFixedSize(390, 800)
    settle()
    assert window.dockWidgetArea(dock) == BOTTOM
    assert abs(window.centralWidget().height() - dock.height()) < 120


def test_other_areas_are_left_alone() -> None:
    window, docks, _ = make(390)
    top = QDockWidget("Top")
    assert docks.added(top, Qt.DockWidgetArea.TopDockWidgetArea) == Qt.DockWidgetArea.TopDockWidgetArea


def test_through_add_dock_widget(monkeypatch) -> None:
    # as installed: the add-on calls QMainWindow.addDockWidget, and moving
    # the dock must not count as the add-on adding it at the bottom
    from kioku import maindocks

    window = QMainWindow()
    window.setCentralWidget(QWidget())
    window.setFixedSize(390, 800)
    window.show()
    monkeypatch.setattr(aqt, "mw", window, raising=False)
    monkeypatch.setattr(QMainWindow, "addDockWidget", QMainWindow.addDockWidget)
    maindocks.install()
    dock = QDockWidget("Reader")
    dock.setWidget(QWidget())
    window.addDockWidget(RIGHT, dock)
    settle()
    assert window.dockWidgetArea(dock) == BOTTOM
    for _ in range(2):
        window.setFixedSize(900, 400)
        settle()
        assert window.dockWidgetArea(dock) == RIGHT
        window.setFixedSize(390, 800)
        settle()
        assert window.dockWidgetArea(dock) == BOTTOM
