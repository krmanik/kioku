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
    # what its title bar needs, not the add-on's 550
    assert dock.minimumWidth() < 100
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
    monkeypatch.setattr(QMainWindow, "splitDockWidget", QMainWindow.splitDockWidget)
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


def installed(monkeypatch, width: int) -> QMainWindow:
    from kioku import maindocks

    window = QMainWindow()
    window.setCentralWidget(QWidget())
    window.setFixedSize(width, 800)
    window.show()
    monkeypatch.setattr(aqt, "mw", window, raising=False)
    monkeypatch.setattr(QMainWindow, "addDockWidget", QMainWindow.addDockWidget)
    monkeypatch.setattr(QMainWindow, "splitDockWidget", QMainWindow.splitDockWidget)
    maindocks.install()
    return window


def panel(title: str) -> QDockWidget:
    dock = QDockWidget(title)
    dock.setWidget(QWidget())
    dock.setMinimumWidth(400)
    return dock


def shown(dock: QDockWidget) -> bool:
    return not dock.visibleRegion().isEmpty()


def test_second_dock_becomes_a_tab(monkeypatch) -> None:
    # Incremento: its reader on the right, then Add Card on the left
    window = installed(monkeypatch, 390)
    reader, add = panel("Reader"), panel("Add Card")
    window.addDockWidget(RIGHT, reader)
    settle()
    window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, add)
    settle()
    assert window.tabifiedDockWidgets(add) == [reader]
    assert shown(add) and not shown(reader)
    assert add.geometry().right() < window.width() and add.width() > 300
    # on a tablet they go back to their sides, untabbed
    window.setFixedSize(1024, 800)
    settle()
    assert window.dockWidgetArea(add) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.dockWidgetArea(reader) == RIGHT
    assert window.tabifiedDockWidgets(add) == []
    window.setFixedSize(390, 800)
    settle()
    assert len(window.tabifiedDockWidgets(add) + window.tabifiedDockWidgets(reader)) == 2


def test_side_by_side_split_becomes_a_tab(monkeypatch) -> None:
    window = installed(monkeypatch, 390)
    reader, other = panel("Reader"), panel("Reference")
    window.addDockWidget(RIGHT, reader)
    settle()
    window.splitDockWidget(reader, other, Qt.Orientation.Horizontal)
    settle()
    assert window.tabifiedDockWidgets(other) == [reader]
    assert shown(other)


def test_tablet_split_stays_side_by_side(monkeypatch) -> None:
    window = installed(monkeypatch, 1024)
    reader, other = panel("Reader"), panel("Reference")
    window.addDockWidget(RIGHT, reader)
    window.splitDockWidget(reader, other, Qt.Orientation.Horizontal)
    settle()
    assert window.tabifiedDockWidgets(other) == []
    assert shown(other) and shown(reader)


def test_expand_over_the_main_view(monkeypatch) -> None:
    window = installed(monkeypatch, 390)
    reader = panel("Reader")
    window.addDockWidget(RIGHT, reader)
    settle()
    docks = window._kioku_docks
    button = docks.buttons[reader]
    assert button.isVisible() and button.text() == "▲"
    button.click()
    settle()
    assert not window.centralWidget().isVisible()
    assert reader.height() > 700
    assert button.text() == "▼"
    button.click()
    settle()
    assert window.centralWidget().isVisible()
    assert abs(window.centralWidget().height() - reader.height()) < 120


def test_expanded_collapses_when_wide_or_closed(monkeypatch) -> None:
    window = installed(monkeypatch, 390)
    reader = panel("Reader")
    window.addDockWidget(RIGHT, reader)
    settle()
    docks = window._kioku_docks
    docks.buttons[reader].click()
    window.setFixedSize(1024, 800)
    settle()
    assert window.centralWidget().isVisible()
    assert not docks.buttons[reader].isVisible()
    window.setFixedSize(390, 800)
    settle()
    docks.buttons[reader].click()
    reader.close()
    settle()
    assert window.centralWidget().isVisible()
