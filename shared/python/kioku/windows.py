"""Phone-friendly top-level windows.

iOS has no window manager: a QDialog or the browser's QMainWindow appears
at its desktop size with no title bar, so it can be wider than the screen
and has no way to close it. Every top-level window except the main window
and popups is therefore made to fill the screen and given a title bar with a
Close button. Message boxes and small dialogs (a login, a text prompt) keep
their own buttons and are shown as a bordered card in the middle of the
screen, as tall as their content.
"""

from __future__ import annotations

import sys
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QMargins, QObject, QRect, QRectF, QSignalBlocker, QSize, Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractScrollArea,
    QBoxLayout,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QScroller,
    QScrollerProperties,
    QSizePolicy,
    QTabBar,
    QTabWidget,
    QWidget,
)

BAR_HEIGHT = 44
BAR_PROPERTY = "kiokuTitleBar"
BORDER_PROPERTY = "kiokuPopupBorder"
# gap between a card-style window and the screen edges
CARD_MARGIN = 8
WINDOW_TYPES = (Qt.WindowType.Window, Qt.WindowType.Dialog, Qt.WindowType.Sheet)


class TitleBar(QWidget):
    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setObjectName(BAR_PROPERTY)
        self.setAutoFillBackground(True)
        self._window = window

        close = QPushButton("‹ " + _back_label(), self)
        close.setFlat(True)
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(lambda: _back(window))
        font = close.font()
        font.setBold(True)
        close.setFont(font)

        self._title = QLabel(self)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        font = self._title.font()
        font.setBold(True)
        self._title.setFont(font)

        # right side: optional action button, else a spacer that keeps the
        # title centred
        self._right = QWidget(self)
        self._right.setFixedWidth(close.sizeHint().width())
        QHBoxLayout(self._right).setContentsMargins(0, 0, 0, 0)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(close)
        layout.addWidget(self._title, 1)
        layout.addWidget(self._right)
        self.update_title()

    def add_action(self, text: str, callback: Any) -> QPushButton:
        button = QPushButton(text, self._right)
        button.setFlat(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(callback)
        self._right.layout().addWidget(button)
        self._right.setFixedWidth(max(self._right.width(), button.sizeHint().width()))
        return button

    def update_title(self) -> None:
        self._title.setText(self._window.windowTitle())

    def place(self, safe_top: int) -> None:
        self.setGeometry(0, safe_top, self._window.width(), BAR_HEIGHT)
        self.raise_()

    def paintEvent(self, evt: Any) -> None:
        super().paintEvent(evt)
        from PyQt6.QtGui import QPainter

        p = QPainter(self)
        p.setPen(self.palette().mid().color())
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class PopupBorder(QWidget):
    """A thin frame around a card-style window, which has no window frame of
    its own and would blend into the screen behind it."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setObjectName(BORDER_PROPERTY)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.place()
        self.show()

    def place(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self.raise_()

    def paintEvent(self, evt: Any) -> None:
        from PyQt6.QtGui import QPainter

        p = QPainter(self)
        p.setPen(self.palette().mid().color())
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))


def _back_label() -> str:
    try:
        from aqt.utils import tr

        return tr.actions_back()
    except Exception:
        return "Back"


def _safe_area(w: QWidget) -> QMargins:
    handle = w.windowHandle()
    if handle is not None and hasattr(handle, "safeAreaMargins"):
        return handle.safeAreaMargins()
    import aqt

    # the main window fills the screen and has no margins of its own
    rect, inner = aqt.mw.rect(), aqt.mw.contentsRect()
    return QMargins(
        inner.left(),
        inner.top(),
        rect.right() - inner.right(),
        rect.bottom() - inner.bottom(),
    )


def _fit_children(w: QWidget, avail: QRect) -> None:
    """Desktop dialogs are laid out for a wide screen: children pinned to a
    minimum size, combo boxes as wide as their longest entry, long one-line
    labels. Relax those so the window fits the phone."""
    narrow = avail.width()
    for child in [w] + w.findChildren(QWidget):
        if child.minimumWidth() > narrow:
            child.setMinimumWidth(0)
        if child.minimumHeight() > avail.height():
            child.setMinimumHeight(0)
        if isinstance(child, QTabWidget):
            _fit_tabs(child, narrow)
        if isinstance(child, QComboBox):
            child.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            child.setMinimumContentsLength(8)
        elif (
            isinstance(child, QDialogButtonBox)
            and child.orientation() == Qt.Orientation.Horizontal
            and child.sizeHint().width() > narrow - 32
        ):
            # a row of long labels ("Download from AnkiWeb") would be clipped
            child.setOrientation(Qt.Orientation.Vertical)
        elif (
            isinstance(child, QLabel)
            and not child.wordWrap()
            and child.pixmap().isNull()
            and child.sizeHint().width() > narrow * 0.6
        ):
            child.setWordWrap(True)
    layout = w.layout()
    if layout is not None and layout.totalMinimumSize().width() > narrow:
        # still too wide: let the window be narrower than its layout wants
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)


TAB_STRIP = "kiokuTabStrip"


class TabStrip(QScrollArea):
    """A copy of a tab widget's tabs in a strip that scrolls sideways with a
    swipe. Qt's own tab bar scrolls only with two small arrow buttons, and
    can't be put in a scroll area: the tab widget places it itself."""

    def __init__(self, tabs: QTabWidget) -> None:
        super().__init__(tabs.parentWidget())
        self.setObjectName(TAB_STRIP)
        self._tabs = tabs
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        bar = self._bar = QTabBar()
        bar.setUsesScrollButtons(False)
        bar.setExpanding(False)
        bar.setElideMode(Qt.TextElideMode.ElideNone)
        bar.setDocumentMode(tabs.documentMode())
        self.setWidget(bar)
        # a drag scrolls; a tap still reaches the tab under it
        QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        props = QScroller.scroller(self.viewport()).scrollerProperties()
        props.setScrollMetric(
            QScrollerProperties.ScrollMetric.HorizontalOvershootPolicy,
            QScrollerProperties.OvershootPolicy.OvershootAlwaysOff,
        )
        QScroller.scroller(self.viewport()).setScrollerProperties(props)
        bar.currentChanged.connect(self._bar_changed)
        tabs.currentChanged.connect(self._tabs_changed)

    def update_tabs(self) -> None:
        tabs, bar = self._tabs, self._bar
        bar.blockSignals(True)
        while bar.count():
            bar.removeTab(0)
        for i in range(tabs.count()):
            bar.addTab(tabs.tabIcon(i), tabs.tabText(i))
            bar.setTabVisible(i, tabs.isTabVisible(i))
        bar.setCurrentIndex(tabs.currentIndex())
        bar.blockSignals(False)
        bar.setFixedSize(bar.sizeHint())
        self.setFixedHeight(bar.height())
        self._show_current()

    def _bar_changed(self, index: int) -> None:
        self._tabs.setCurrentIndex(index)
        self._show_current()

    def _tabs_changed(self, index: int) -> None:
        if self._bar.currentIndex() != index:
            self._bar.setCurrentIndex(index)

    def _show_current(self) -> None:
        rect = self._bar.tabRect(self._bar.currentIndex())
        if rect.isValid():
            self.ensureVisible(rect.center().x(), rect.center().y(), rect.width() // 2 + 24, 0)


def _fit_tabs(tabs: QTabWidget, narrow: int) -> None:
    """Tabs wider than the screen (Preferences has eight) get a strip that
    scrolls with a swipe in place of Qt's tab bar; Qt's again when they fit
    (landscape)."""
    parent = tabs.parentWidget()
    if parent is None:
        return
    strip = next(
        (
            c
            for c in parent.findChildren(
                TabStrip, TAB_STRIP, Qt.FindChildOption.FindDirectChildrenOnly
            )
            if c._tabs is tabs
        ),
        None,
    )
    _scroll_pages(tabs)
    fits = tabs.tabBar().sizeHint().width() <= narrow - 2 * CARD_MARGIN
    if strip is None:
        box = parent.layout()
        if fits or not isinstance(box, QBoxLayout) or box.indexOf(tabs) < 0:
            return
        strip = TabStrip(tabs)
        box.insertWidget(box.indexOf(tabs), strip)
    tabs.tabBar().setVisible(fits)
    strip.setVisible(not fits)
    strip.update_tabs()


SCROLL_PAGE = "kiokuScrollPage"


def _scroll_pages(tabs: QTabWidget) -> None:
    """Tab pages are laid out for a desktop's height: on a phone in
    landscape, or with a larger user interface size, Qt squeezed their
    rows on top of each other. Each page scrolls instead, with a drag (also
    sideways, if a page can't get as narrow as the screen)."""
    current = tabs.currentIndex()
    blocker = QSignalBlocker(tabs)
    for i in range(tabs.count()):
        page = tabs.widget(i)
        if isinstance(page, QAbstractScrollArea) or page.objectName() == SCROLL_PAGE:
            continue
        scroll = QScrollArea()
        scroll.setObjectName(SCROLL_PAGE)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        for policy in (scroll.setHorizontalScrollBarPolicy, scroll.setVerticalScrollBarPolicy):
            policy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        icon, text, visible = tabs.tabIcon(i), tabs.tabText(i), tabs.isTabVisible(i)
        tabs.removeTab(i)
        scroll.setWidget(page)
        tabs.insertTab(i, scroll, icon, text)
        tabs.setTabVisible(i, visible)
        QScroller.grabGesture(scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
    tabs.setCurrentIndex(current)
    del blocker


def _is_small_dialog(w: QWidget, avail: QRect) -> bool:
    """A dialog with its own buttons and little content (the AnkiWeb login,
    a rename prompt). Filling the screen spreads it out: its text at the
    top, its buttons at the bottom. Lists, text areas and web pages make
    use of the space, so dialogs with those still fill the screen."""
    if sip.isdeleted(w) or not isinstance(w, QDialog) or w.findChild(QDialogButtonBox) is None:
        return False
    for child in w.findChildren(QWidget):
        if (isinstance(child, QAbstractScrollArea) and not isinstance(child, TabStrip)) or any(
            c.__name__ == "QWebEngineView" for c in type(child).__mro__
        ):
            return False
    return _card_size(w, avail).height() <= avail.height() * 0.7


def _add_cancel(w: QWidget) -> None:
    """Anki's progress window has no buttons (on the desktop, its window's
    close button cancels a sync or Check Media), so it filled the screen and
    flashed on every sync. With a Cancel button it is a small card."""
    layout = w.layout()
    if layout is None:
        return
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, w)
    buttons.rejected.connect(w.close)
    layout.addWidget(buttons)


def _card_size(w: QWidget, avail: QRect) -> QSize:
    width = min(avail.width() - 2 * CARD_MARGIN, max(w.sizeHint().width(), 480))
    layout = w.layout()
    height = -1
    if layout is not None and layout.hasHeightForWidth():
        height = layout.totalHeightForWidth(width)
    if height <= 0:
        height = w.sizeHint().height()
    return QSize(width, min(height, avail.height() - 2 * CARD_MARGIN))


def _available() -> QRect:
    screen = QGuiApplication.primaryScreen()
    return screen.availableGeometry() if screen is not None else QRect(0, 0, 400, 800)


def _above_keyboard(avail: QRect) -> QRect:
    """The part of the screen the on-screen keyboard leaves free."""
    im = QGuiApplication.inputMethod()
    kbd = im.keyboardRectangle() if im is not None and im.isVisible() else None
    if kbd is None or kbd.isEmpty():
        return avail
    screen = QGuiApplication.primaryScreen()
    if sys.platform == "android" and screen is not None:
        # Android reports it in device pixels
        ratio = screen.devicePixelRatio()
        kbd = QRectF(kbd.topLeft() / ratio, kbd.size() / ratio)
    top = int(kbd.top())
    # a floating keyboard covers only part of the width; leave cards alone
    if kbd.width() >= avail.width() * 0.9 and avail.top() < top < avail.bottom():
        return QRect(avail.x(), avail.y(), avail.width(), top - avail.y())
    return avail


def keyboard_overlap(w: QWidget) -> int:
    """How much of the window the on-screen keyboard covers. Qt on Android
    puts it into the window's safe area only for a moment (its insets come
    from the activity's adjustResize, then go back), so the Add window's
    buttons and tags ended up under the keyboard, after being laid out
    above it and back. (iOS keeps its own handling.)"""
    if sys.platform != "android":
        return 0
    avail = _available()
    free = _above_keyboard(avail)
    if free == avail:
        return 0
    return max(0, w.geometry().bottom() - free.bottom())


def _center(w: QWidget, size: QSize, avail: QRect) -> None:
    area = _above_keyboard(avail)
    y = area.y() + (area.height() - size.height()) // 2
    w.setGeometry(
        avail.x() + (avail.width() - size.width()) // 2,
        max(avail.y() + CARD_MARGIN, y) if size.height() <= area.height() else area.bottom() - size.height(),
        size.width(),
        size.height(),
    )


class WindowManager(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        app.installEventFilter(self)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            screen.availableGeometryChanged.connect(self._refit_all)
        im = QGuiApplication.inputMethod()
        if im is not None:
            # keep cards with a text field (the AnkiWeb login) above it, and
            # windows' contents (the Add window's buttons)
            for changed in (im.keyboardRectangleChanged, im.visibleChanged):
                changed.connect(self._recenter_cards)
                changed.connect(self._relayout_windows)

    def eventFilter(self, obj: QObject | None, evt: QEvent | None) -> bool:
        if evt is None or not isinstance(obj, QWidget):
            return False
        kind = evt.type()
        if kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if evt.key() == Qt.Key.Key_Back:  # type: ignore[attr-defined]
                # Android's Back: unhandled, it finishes the activity and
                # quits Anki
                if kind == QEvent.Type.KeyRelease:
                    _go_back()
                return True
            return False
        if kind == QEvent.Type.Show and obj.isWindow():
            import aqt

            if self._manageable(obj):
                # after the window's own show logic (e.g. restoring geometry)
                QTimer.singleShot(0, lambda w=obj: self._adopt(w))
            elif obj is aqt.mw:
                # after loadProfile's raise_(): a message that came up while
                # the main window was hidden (a sync error while switching
                # profiles) was left under it, unseen but blocking every tap
                QTimer.singleShot(0, _raise_modal)
        elif kind == QEvent.Type.Resize and obj.isWindow():
            if self._bar(obj) is not None:
                self._layout(obj)
            border = self._border(obj)
            if border is not None:
                border.place()
        elif kind == QEvent.Type.WindowTitleChange:
            bar = self._bar(obj)
            if bar is not None:
                bar.update_title()
        return False

    def _manageable(self, w: QWidget) -> bool:
        import aqt

        if w is aqt.mw or isinstance(w, QMenu):
            return False
        return w.windowType() in WINDOW_TYPES

    @staticmethod
    def _bar(w: QWidget) -> TitleBar | None:
        bar = w.findChild(TitleBar, BAR_PROPERTY, Qt.FindChildOption.FindDirectChildrenOnly)
        return bar

    @staticmethod
    def _border(w: QWidget) -> PopupBorder | None:
        return w.findChild(PopupBorder, BORDER_PROPERTY, Qt.FindChildOption.FindDirectChildrenOnly)

    def _adopt(self, w: QWidget) -> None:
        if sip.isdeleted(w) or not w.isVisible():
            return
        avail = _available()
        _fit_children(w, avail)
        if isinstance(w, QMessageBox):
            self._fit_message_box(w, avail)
            self._add_border(w)
            return
        if type(w).__name__ == "ProgressDialog" and w.findChild(QDialogButtonBox) is None:
            _add_cancel(w)
        if self._bar(w) is None and _is_small_dialog(w, avail):
            w.setMinimumSize(0, 0)
            _center(w, _card_size(w, avail), avail)
            self._add_border(w)
            return
        if self._bar(w) is None:
            # we add the safe area ourselves (Qt would merge it with our
            # margins by taking the larger, hiding the title bar)
            w.setAttribute(Qt.WidgetAttribute.WA_ContentsMarginsRespectsSafeArea, False)
            # remember the window's own margins; ours are added on top
            m = w.contentsMargins()
            w.setProperty("kiokuMargins", (m.left(), m.top(), m.right(), m.bottom()))
            bar = TitleBar(w)
            bar.show()
            adapt = ADAPTERS.get(type(w).__name__)
            if adapt is not None:
                adapt(w, bar)
        w.setMinimumSize(0, 0)
        w.setGeometry(avail)
        self._layout(w)

    def _layout(self, w: QWidget) -> None:
        """Margins = safe area + the window's own + the title bar. Qt merges
        user margins with the safe area by taking the larger of the two, so
        the safe area has to be included explicitly."""
        bar = self._bar(w)
        if bar is None:
            return
        own = w.property("kiokuMargins") or (0, 0, 0, 0)
        safe = _safe_area(w)
        margins = (
            safe.left() + own[0],
            safe.top() + own[1] + BAR_HEIGHT,
            safe.right() + own[2],
            max(safe.bottom(), keyboard_overlap(w)) + own[3],
        )
        current = w.contentsMargins()
        if (current.left(), current.top(), current.right(), current.bottom()) != margins:
            w.setContentsMargins(*margins)
        bar.place(safe.top())

    def _relayout_windows(self) -> None:
        for w in QApplication.topLevelWidgets():
            if w.isVisible() and self._bar(w) is not None:
                self._layout(w)

    def _add_border(self, w: QWidget) -> None:
        if self._border(w) is None:
            PopupBorder(w)

    @staticmethod
    def _fit_message_box(box: QMessageBox, avail: QRect) -> None:
        """QMessageBox sizes itself when shown and wraps its text at half
        the screen's width (a desktop rule), so long texts (the sync
        conflict) ran off the bottom. Widen the text label to the screen;
        the box then computes the height the wrapped text needs."""
        label = box.findChild(QLabel, "qt_msgbox_label")
        if label is not None:
            extra = box.width() - label.width()
            label.setMinimumWidth(max(0, avail.width() - 2 * CARD_MARGIN - extra))
            box.setText(box.text())  # makes QMessageBox recompute its size
        height = min(box.height(), avail.height() - 2 * CARD_MARGIN)
        _center(box, QSize(box.width(), height), avail)

    def _recenter_cards(self) -> None:
        avail = _available()
        for w in QApplication.topLevelWidgets():
            if w.isVisible() and self._border(w) is not None:
                _center(w, w.size(), avail)

    def _refit_all(self) -> None:
        for w in QApplication.topLevelWidgets():
            if w.isVisible() and self._manageable(w):
                self._adopt(w)


def _phone_width() -> bool:
    return _available().width() < 600


def adapt_browser(browser: Any, bar: TitleBar) -> None:
    """The sidebar takes half a phone screen: start hidden in portrait and
    give it a title bar button; when shown, let it cover most of the width."""
    from aqt.utils import tr

    dock = browser.sidebarDockWidget

    def toggle() -> None:
        show = not dock.isVisible()
        browser.showSidebar(show)
        if show and _phone_width():
            browser.resizeDocks(
                [dock], [int(_available().width() * 0.8)], Qt.Orientation.Horizontal
            )

    bar.add_action(tr.browsing_sidebar(), toggle)
    # the sidebar's edge (a few px wide) was too thin to drag with a finger
    browser.setStyleSheet(
        browser.styleSheet() + " QMainWindow::separator { width: 16px; height: 16px; }"
    )
    if _phone_width():
        browser.showSidebar(False)
        _wrap_search_row(browser)
        # the cards list and editor need 238px: beside the sidebar that made
        # the window wider than the screen, its Sidebar button went off the
        # edge and the sidebar couldn't be dragged wider
        browser.centralWidget().setMinimumWidth(1)


def _wrap_search_row(browser: Any) -> None:
    """Add-on buttons beside the search box (AMBOSS: Start Qbank session)
    ran past the screen's edge and squeezed the search box: give them a row
    of their own below it."""
    grid = browser.form.gridLayout
    extras = []
    for i in range(grid.count()):
        w = grid.itemAt(i).widget()
        row, col, _, _ = grid.getItemPosition(i)
        # column 0: the cards/notes switch, 1: the search box
        if w is not None and row == 0 and col > 1:
            extras.append(w)
    if not extras:
        return
    box = QHBoxLayout()
    for w in extras:
        grid.removeWidget(w)
        box.addWidget(w)
    grid.addLayout(box, 1, 0, 1, 2)


ADAPTERS = {"Browser": adapt_browser}

_manager: WindowManager | None = None


def _go_back() -> None:
    """Close the topmost popup or window; on the main window, leave the app
    running in the background like other Android apps."""
    import aqt

    w = (
        QApplication.activePopupWidget()
        or QApplication.activeModalWidget()
        or QApplication.activeWindow()
    )
    if w is None or w is aqt.mw:
        import kioku_platform

        move_to_back = getattr(kioku_platform, "move_to_back", None)
        if move_to_back is not None:
            move_to_back()
        return
    _back(w)


def _back(w: QWidget) -> None:
    """Back closes the window, except Anki's profile window: closing that
    quits Anki, which a phone app must not do (Switch Profile, then Back,
    ended the app). Reopen the last profile instead; at start-up, before
    any profile was opened, stay."""
    import aqt

    if type(w).__name__ != "ProfileManager":
        w.close()
        return
    mw = aqt.mw
    profiles = mw.pm.profiles()
    name = mw.pm.last_loaded_profile_name()
    if name in profiles:
        mw.profileForm.profiles.setCurrentRow(profiles.index(name))
        mw.onOpenProfile()


class EnterKeyFilter(QObject):
    """Android: Qt reports a "Next" enter key for single-line fields that
    have another widget after them, so the keyboard shows Next and moves the
    focus instead of sending Return: Browse's search, prompts and the
    AnkiWeb login could not be submitted from the keyboard. Report "Done",
    which sends Return."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.InputMethodQuery
            and isinstance(obj, (QLineEdit, QComboBox, QAbstractSpinBox))
            and event.queries() & Qt.InputMethodQuery.ImEnterKeyType
        ):
            obj.event(event)
            event.setValue(
                Qt.InputMethodQuery.ImEnterKeyType, Qt.EnterKeyType.EnterKeyDone.value
            )
            return True
        return False


_enter_key_filter: EnterKeyFilter | None = None


def _raise_modal() -> None:
    modal = QApplication.activeModalWidget()
    if modal is not None:
        modal.raise_()


def install(app: QApplication) -> None:
    global _manager, _enter_key_filter
    _manager = WindowManager(app)
    if sys.platform == "android":
        _enter_key_filter = EnterKeyFilter(app)
        app.installEventFilter(_enter_key_filter)
