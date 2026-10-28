"""Stacking add-ons' side docks under Anki's main view on narrow screens.

Add-ons such as Incremento put their readers into QDockWidgets on the left
or right of the main window, with desktop widths that leave a phone's main
view a sliver and run off the screen; install() gives Anki's main window a
MainDocks (the native apps through kioku.patches, the Termux variant from
launch_anki.py).
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtWidgets import QDockWidget, QMainWindow

SIDES = (Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.RightDockWidgetArea)

# Qt's own, for moving docks: install() replaces QMainWindow.addDockWidget
_add_dock_widget = QMainWindow.addDockWidget


class MainDocks(QObject):
    """Docks added on the left or right stay there when the window is at
    least NARROW points wide (tablets, phones in landscape), with their
    minimum widths capped at a third; narrower they go to the bottom,
    sharing the height evenly with the main view, and come back when the
    window is wide again."""

    NARROW = 600

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self.window = window
        # dock -> (the side it was added on, its own minimum width)
        self.docks: dict[QDockWidget, tuple[Qt.DockWidgetArea, int]] = {}
        self.stacked: bool | None = None
        # a rotation resizes the window in steps: adapt once they're over
        self.settled = QTimer(self)
        self.settled.setSingleShot(True)
        self.settled.setInterval(200)
        self.settled.timeout.connect(self.adapt)
        window.installEventFilter(self)

    def added(self, dock: QDockWidget, area: Qt.DockWidgetArea) -> Qt.DockWidgetArea:
        """The area to add `dock` in, for QMainWindow.addDockWidget."""
        if area not in SIDES:
            self.docks.pop(dock, None)
            return area
        if dock not in self.docks:
            # not self: the window and this object may be gone by then
            docks = self.docks
            dock.destroyed.connect(lambda _=None, d=dock: docks.pop(d, None))
            dock.visibilityChanged.connect(lambda shown, d=dock: shown and self.fit(d))
        self.docks[dock] = (area, self.docks.get(dock, (area, dock.minimumWidth()))[1])
        QTimer.singleShot(0, lambda: self.fit(dock))
        return Qt.DockWidgetArea.BottomDockWidgetArea if self.narrow() else area

    def narrow(self) -> bool:
        width = self.window.width()
        screen = self.window.screen()
        if screen is not None:
            width = min(width, screen.availableGeometry().width())
        return width < self.NARROW

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        # getattr: the window can still send events while it is destroyed
        if obj is getattr(self, "window", None) and event is not None and (
            event.type() == QEvent.Type.Resize
        ):
            self.settled.start()
        return False

    def adapt(self) -> None:
        stacked = self.narrow()
        if stacked == self.stacked:
            return
        self.stacked = stacked
        for dock, (side, _) in list(self.docks.items()):
            area = Qt.DockWidgetArea.BottomDockWidgetArea if stacked else side
            if self.window.dockWidgetArea(dock) != area and not dock.isFloating():
                _add_dock_widget(self.window, area, dock)
            # once the window has laid out the moved dock
            QTimer.singleShot(0, lambda d=dock: self.fit(d))

    def fit(self, dock: QDockWidget) -> None:
        if dock not in self.docks or not dock.isVisible():
            return
        original = self.docks[dock][1]
        if self.narrow():
            dock.setMinimumWidth(0)
            central = self.window.centralWidget()
            if central is not None and (
                self.window.dockWidgetArea(dock) == Qt.DockWidgetArea.BottomDockWidgetArea
            ):
                half = (central.height() + dock.height()) // 2
                self.window.resizeDocks([dock], [half], Qt.Orientation.Vertical)
        else:
            dock.setMinimumWidth(min(original, self.window.width() // 3))


def install() -> None:
    import aqt

    def add_dock_widget(self, area, dock, *args):  # type: ignore[no-untyped-def]
        if self is aqt.mw:
            if not hasattr(self, "_kioku_docks"):
                self._kioku_docks = MainDocks(self)
            area = self._kioku_docks.added(dock, area)
        _add_dock_widget(self, area, dock, *args)

    QMainWindow.addDockWidget = add_dock_widget
