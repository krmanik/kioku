"""Anki's web views reach the edges of the screen.

The main window kept out of the phone's whole safe area: the home indicator
(iPhone) or gesture bar (Android) at the bottom and, in landscape, the
notch's side and the one opposite. That left strips of plain window colour
beside and under the pages; a background image (the Custom background
add-on) stopped short of the edges. Now the top bar, the main view and the
bottom bar fill those strips and pad their pages by the same amount, so
text and buttons stay clear of the notch and the home indicator. The menu
bar keeps its margins. While the bottom bar is hidden (Preferences › Hide
bottom bar during review) the window keeps out of the bottom safe area as
before.

Android: while the on-screen keyboard is open the window keeps out of the
part it covers (windows.keyboard_overlap), as Kioku's other windows do. The
window keeps its size (windows._fill_main), so Android 11 to 14 left the
bottom bar (Show Answer) under the keyboard when the reviewer's typing box
had it open.
"""

from __future__ import annotations

from typing import Any

import aqt
from aqt import gui_hooks
from aqt.qt import QEvent, QGuiApplication, QObject, QSize, Qt, QTimer, QWidget, sip
from PyQt6.QtWebEngineCore import QWebEngineScript

from . import windows

STYLE_ID = "kioku-edges"
SIDES = ("left", "right", "bottom")
EVENTS = (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.Hide)


def apply() -> None:
    gui_hooks.main_window_did_init.append(lambda: ScreenEdges(aqt.mw))


def padding_css(insets: dict[str, int]) -> str:
    """Padding on <html>, which Anki's pages leave alone (the reviewer's
    bottom bar sets body padding to 0). The properties let a rotation change
    it without reloading the page."""
    rules = " ".join(
        f"padding-{side}: var(--kioku-safe-{side}, {insets.get(side, 0)}px);" for side in SIDES
    )
    return f'<style id="{STYLE_ID}">html {{ {rules} }}</style>'


def _update_js(insets: dict[str, int]) -> str:
    """Set the properties on the page shown now, and add the style to pages
    that weren't made with stdHtml (Anki's congrats page)."""
    props = "".join(
        f"s.setProperty('--kioku-safe-{side}', '{insets.get(side, 0)}px');" for side in SIDES
    )
    css = padding_css(insets).replace(f'<style id="{STYLE_ID}">', "").replace("</style>", "")
    return (
        "(function(){var s=document.documentElement.style;" + props +
        f"if(!document.getElementById('{STYLE_ID}')){{var e=document.createElement('style');"
        f"e.id='{STYLE_ID}';e.textContent={css!r};"
        "(document.head||document.documentElement).appendChild(e);}})();"
    )


class _View:
    """One of the three web views and the sides it reaches into."""

    def __init__(self, web: Any, sides: tuple[str, ...]) -> None:
        self.web = web
        self.sides = sides
        self.insets: dict[str, int] = {}
        self.script: Any = None
        std_html = web.stdHtml

        def with_padding(body: str, *args: Any, **kwargs: Any) -> None:
            # stdHtml(body, css, js, head, context, ...)
            if len(args) >= 3:
                args = args[:2] + (args[2] + padding_css(self.insets),) + args[3:]
            else:
                kwargs["head"] = kwargs.get("head", "") + padding_css(self.insets)
            std_html(body, *args, **kwargs)

        web.stdHtml = with_padding

    def set(self, safe: dict[str, int]) -> bool:
        insets = {side: safe[side] for side in self.sides if safe[side]}
        if insets == self.insets:
            return False
        self.insets = insets
        js = _update_js(insets)
        scripts = self.web.page().scripts()
        if self.script is not None:
            scripts.remove(self.script)
        self.script = QWebEngineScript()
        self.script.setName(STYLE_ID)
        self.script.setSourceCode(js)
        self.script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        self.script.setRunsOnSubFrames(False)
        scripts.insert(self.script)
        self.web.eval(js)
        return True


class _Spacer(QWidget):
    """The menu bar sizes corner widgets by their size hint."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.hint = QSize(0, 0)
        self.setFixedSize(self.hint)

    def sizeHint(self) -> QSize:
        return self.hint


class ScreenEdges(QObject):
    def __init__(self, mw: Any) -> None:
        super().__init__(mw)
        self.mw = mw
        self.top = _View(mw.toolbarWeb, ("left", "right"))
        self.main = _View(mw.web, ("left", "right"))
        self.bottom = _View(mw.bottomWeb, SIDES)
        # the menu bar lays its menus out ignoring contents margins; empty
        # corner widgets keep them clear of the notch
        self.corners: dict[Qt.Corner, _Spacer] = {}
        bar = mw.menuBar()
        for corner in (Qt.Corner.TopLeftCorner, Qt.Corner.TopRightCorner):
            if bar.cornerWidget(corner) is None:
                spacer = _Spacer(bar)
                bar.setCornerWidget(spacer, corner)
                spacer.show()
                self.corners[corner] = spacer
        self.watching = False
        self._pending = False
        mw.installEventFilter(self)
        mw.bottomWeb.installEventFilter(self)
        im = QGuiApplication.inputMethod()
        if im is not None:
            for changed in (im.keyboardRectangleChanged, im.visibleChanged):
                changed.connect(self._schedule)
        self.update()

    def _schedule(self, *_args: Any) -> None:
        if not self._pending:
            self._pending = True
            QTimer.singleShot(0, self.update)

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if event.type() in EVENTS:
            self._schedule()
        return False

    def update(self) -> None:
        self._pending = False
        mw = self.mw
        if sip.isdeleted(mw) or sip.isdeleted(mw.bottomWeb):
            return
        handle = mw.windowHandle()
        if handle is None or not hasattr(handle, "safeAreaMargins"):
            return  # Qt keeps the window inside the safe area until then
        if not self.watching:
            self.watching = True
            mw.setAttribute(Qt.WidgetAttribute.WA_ContentsMarginsRespectsSafeArea, False)
            if hasattr(handle, "safeAreaMarginsChanged"):
                handle.safeAreaMarginsChanged.connect(lambda _m: self.update())
        safe = handle.safeAreaMargins()
        bar = mw.bottomWeb
        # Anki "hides" the bar by shrinking it to 1 px (`hidden`)
        covered = not bar.isHidden() and not getattr(bar, "hidden", False)
        shown = covered
        keyboard = windows.keyboard_overlap(mw)
        if keyboard:
            # the bar sits on the keyboard, which covers the gesture bar
            covered = False
        mw.setContentsMargins(0, safe.top(), 0, keyboard or (0 if covered else safe.bottom()))
        self._pad_menu_bar(safe.left(), safe.right())
        sides = {"left": safe.left(), "right": safe.right(), "bottom": safe.bottom()}
        self.top.set(sides)
        self.main.set(sides)
        if self.bottom.set(sides if covered else {**sides, "bottom": 0}) and shown:
            bar.adjustHeightToFit()

    def _pad_menu_bar(self, left: int, right: int) -> None:
        widths = {Qt.Corner.TopLeftCorner: left, Qt.Corner.TopRightCorner: right}
        changed = False
        for corner, spacer in self.corners.items():
            if spacer.hint.width() != widths[corner]:
                spacer.hint = QSize(widths[corner], 0)
                spacer.setFixedSize(spacer.hint)
                changed = True
        if changed:
            bar = self.mw.menuBar()
            # re-place the corner widgets and menus
            bar.resize(bar.width() + 1, bar.height())
            bar.resize(bar.width() - 1, bar.height())
