"""Stacking add-ons' side docks under Anki's main view on narrow screens.

Add-ons such as Incremento put their readers into QDockWidgets on the left
or right of the main window, with desktop widths that leave a phone's main
view a sliver and run off the screen; install() gives Anki's main window a
MainDocks (the native apps through kioku.patches, the Termux variant from
launch_anki.py).
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtWidgets import QDockWidget, QMainWindow, QToolButton

SIDES = (Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.RightDockWidgetArea)

# Qt's own, for moving docks: install() replaces both
_add_dock_widget = QMainWindow.addDockWidget
_split_dock_widget = QMainWindow.splitDockWidget


class MainDocks(QObject):
    """Docks added on the left or right stay there when the window is at
    least NARROW points wide (tablets, phones in landscape), with their
    minimum widths capped at a third; narrower they go to the bottom,
    sharing the height evenly with the main view, and come back when the
    window is wide again. Side by side at the bottom they would each get a
    sliver of the width (Incremento's Add Card panel next to its reader), so
    there they become tabs of one dock, the newest in front. A button in the
    title bar of a stacked dock expands it over the main view (▲: Incremento's
    reader opens tools below its own controls) or splits again (▼)."""

    NARROW = 600
    TITLE = 28

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self.window = window
        # dock -> (the side it was added on, its own minimum width)
        self.docks: dict[QDockWidget, tuple[Qt.DockWidgetArea, int]] = {}
        self.stacked: bool | None = None
        self.expanded = False
        self.buttons: dict[QDockWidget, QToolButton] = {}
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
            docks, buttons = self.docks, self.buttons
            dock.destroyed.connect(
                lambda _=None, d=dock: (docks.pop(d, None), buttons.pop(d, None))
            )
            dock.visibilityChanged.connect(lambda shown, d=dock: self.shown(d, shown))
            button = QToolButton(dock)
            button.setAutoRaise(True)
            button.clicked.connect(lambda: self.set_expanded(not self.expanded))
            button.hide()
            self.buttons[dock] = button
            dock.installEventFilter(self)
        self.docks[dock] = (area, self.docks.get(dock, (area, dock.minimumWidth()))[1])
        QTimer.singleShot(0, lambda: self.fit(dock))
        return Qt.DockWidgetArea.BottomDockWidgetArea if self.narrow() else area

    def stack(self, dock: QDockWidget) -> None:
        """After `dock` went to the bottom: a tab of the docks already there."""
        if not self.narrow() or dock.isFloating():
            return
        bottom = Qt.DockWidgetArea.BottomDockWidgetArea
        if self.window.dockWidgetArea(dock) != bottom:
            return
        for other in self.docks:
            if (
                other is not dock
                and not other.isFloating()
                and not other.isHidden()
                and self.window.dockWidgetArea(other) == bottom
            ):
                self.window.tabifyDockWidget(other, dock)
                # once the tab bar is there
                QTimer.singleShot(0, dock.raise_)
                return

    def split(self, first: QDockWidget, second: QDockWidget, orientation: Qt.Orientation) -> bool:
        """For QMainWindow.splitDockWidget: True when `second` became a tab
        of `first` instead of a pane beside it."""
        if (
            orientation != Qt.Orientation.Horizontal
            or not self.narrow()
            or self.window.dockWidgetArea(first) != Qt.DockWidgetArea.BottomDockWidgetArea
        ):
            return False
        if second not in self.docks:
            self.added(second, self.docks.get(first, (Qt.DockWidgetArea.RightDockWidgetArea, 0))[0])
        self.window.tabifyDockWidget(first, second)
        QTimer.singleShot(0, second.raise_)
        return True

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
        elif obj in self.buttons and event is not None and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            self.place(obj)  # type: ignore[arg-type]
        return False

    def shown(self, dock: QDockWidget, shown: bool) -> None:
        if shown:
            self.fit(dock)
        elif self.expanded and not any(d.isVisible() for d in self.docks):
            # the last dock closed: nothing would be left on the screen
            self.set_expanded(False)
        self.update_buttons()

    def set_expanded(self, on: bool) -> None:
        self.expanded = on
        # the docks' height to split, before the main view takes its part
        shown = [d for d in self.docks if d.isVisible()]
        height = max((d.height() for d in shown), default=0)
        central = self.window.centralWidget()
        if central is not None:
            central.setVisible(not on)
        if not on and shown and height:
            self.window.resizeDocks(shown, [height // 2] * len(shown), Qt.Orientation.Vertical)
        self.update_buttons()

    def update_buttons(self) -> None:
        bottom = Qt.DockWidgetArea.BottomDockWidgetArea
        for dock, button in self.buttons.items():
            stacked = (
                self.narrow()
                and not dock.isFloating()
                and self.window.dockWidgetArea(dock) == bottom
            )
            button.setText("▼" if self.expanded else "▲")
            button.setToolTip("Split" if self.expanded else "Expand")
            button.setVisible(stacked)
            if stacked:
                self.place(dock)

    def place(self, dock: QDockWidget) -> None:
        button = self.buttons[dock]
        content = dock.widget()
        height = content.geometry().top() if content is not None else 0
        height = height if height > 0 else self.TITLE
        button.setFixedSize(height * 2, height)
        button.move((dock.width() - height * 2) // 2, 0)
        button.raise_()

    def adapt(self) -> None:
        stacked = self.narrow()
        if stacked == self.stacked:
            return
        self.stacked = stacked
        if not stacked and self.expanded:
            self.set_expanded(False)
        for dock, (side, _) in list(self.docks.items()):
            area = Qt.DockWidgetArea.BottomDockWidgetArea if stacked else side
            if self.window.dockWidgetArea(dock) != area and not dock.isFloating():
                _add_dock_widget(self.window, area, dock)
                self.stack(dock)
            # once the window has laid out the moved dock
            QTimer.singleShot(0, lambda d=dock: self.fit(d))
        QTimer.singleShot(0, self.update_buttons)

    def fit(self, dock: QDockWidget) -> None:
        if dock not in self.docks or not dock.isVisible():
            return
        original = self.docks[dock][1]
        if self.narrow():
            dock.setMinimumWidth(0)
            central = self.window.centralWidget()
            if central is not None and not self.expanded and (
                self.window.dockWidgetArea(dock) == Qt.DockWidgetArea.BottomDockWidgetArea
            ):
                half = (central.height() + dock.height()) // 2
                self.window.resizeDocks([dock], [half], Qt.Orientation.Vertical)
        else:
            dock.setMinimumWidth(min(original, self.window.width() // 3))


def install() -> None:
    import aqt

    def docks(window: QMainWindow) -> MainDocks | None:
        if window is not aqt.mw:
            return None
        if not hasattr(window, "_kioku_docks"):
            window._kioku_docks = MainDocks(window)  # type: ignore[attr-defined]
        return window._kioku_docks  # type: ignore[attr-defined]

    def add_dock_widget(self, area, dock, *args):  # type: ignore[no-untyped-def]
        main = docks(self)
        if main is not None:
            area = main.added(dock, area)
        _add_dock_widget(self, area, dock, *args)
        if main is not None:
            main.stack(dock)

    def split_dock_widget(self, first, second, orientation):  # type: ignore[no-untyped-def]
        main = docks(self)
        if main is None or not main.split(first, second, orientation):
            _split_dock_widget(self, first, second, orientation)

    QMainWindow.addDockWidget = add_dock_widget
    QMainWindow.splitDockWidget = split_dock_widget
