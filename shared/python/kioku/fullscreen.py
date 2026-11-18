"""View › Full Screen on a touch screen.

In full screen Anki hides the menu bar and shows it again when the mouse
leaves the main web view. A tap doesn't do that (only a swipe does), and the
window stayed in full screen then, so the next View › Full Screen only left
it. Here a swipe to the right on a page asks whether to exit full screen;
entering full screen says so in Anki's tooltip. Nothing is added to the
layout, and the page sees its touches as before.
"""

from __future__ import annotations

from typing import Any

import aqt
import aqt.main
import aqt.utils
from aqt import gui_hooks
from aqt.qt import QMessageBox, Qt

GUIDE_SECONDS = 5
TIP = "Swipe right to exit full screen"
# off on the iPad: a swipe from the left edge shows its window list there,
# and its menu bar (View › Show Toolbars) is always at hand (patches.py)
SWIPE = True
COMMAND = "kioku:swipe-right"

# A quick, mostly sideways swipe of one finger to the right that scrolls
# nothing: not on something that can still scroll that way (a wide table,
# a wide page), not while anything scrolls, zoomed in or text is selected.
# Only listens, so the page sees its touches as before.
SWIPE_RIGHT = r"""
<script>
(function () {
    var start = null, scrolled = false;
    function canScrollOn(el) {
        var page = document.scrollingElement || document.documentElement;
        for (; el; el = el.parentElement) {
            var x = getComputedStyle(el).overflowX;
            var scrolls = el === page ? x !== "hidden" : x === "auto" || x === "scroll";
            if (scrolls && el.scrollLeft > 0) return true;
        }
        return false;
    }
    function zoomed() {
        return window.visualViewport && window.visualViewport.scale > 1.01;
    }
    document.addEventListener("touchstart", function (e) {
        var t = e.touches[0];
        scrolled = false;
        start = e.touches.length === 1 && !canScrollOn(e.target) && !zoomed()
            ? [t.clientX, t.clientY, Date.now()] : null;
    }, {passive: true, capture: true});
    document.addEventListener("scroll", function () { scrolled = true; },
        {passive: true, capture: true});
    document.addEventListener("touchend", function (e) {
        if (!start || e.touches.length) return;
        var t = e.changedTouches[0];
        var dx = t.clientX - start[0], dy = t.clientY - start[1];
        var quick = Date.now() - start[2] < 800;
        start = null;
        if (dx > 60 && Math.abs(dy) < dx / 2 && quick && !scrolled
                && !String(window.getSelection())) {
            pycmd("%s");
        }
    }, {passive: true, capture: true});
})();
</script>
""" % COMMAND


def apply() -> None:
    show_menubar = aqt.main.AnkiQt.show_menubar
    toggle = aqt.main.AnkiQt.on_toggle_full_screen

    def show_menubar_leaving(self: Any) -> None:
        if self.fullscreen:  # the mouse left the main web view
            _leave(self)
        show_menubar(self)

    def toggle_with_guide(self: Any) -> None:
        app = self.app
        if app.activeWindow() is None:
            # Anki toggles app.activeWindow(), and there is none while the
            # iPad's menu bar has the focus: toggle the main window then
            app.activeWindow = lambda: self
            try:
                toggle(self)
            finally:
                del app.activeWindow
        else:
            toggle(self)
        if self.fullscreen:
            aqt.utils.tooltip(TIP, period=GUIDE_SECONDS * 1000, parent=self)
        else:
            aqt.utils.closeTooltip()

    aqt.main.AnkiQt.show_menubar = show_menubar_leaving
    aqt.main.AnkiQt.on_toggle_full_screen = toggle_with_guide
    gui_hooks.webview_will_set_content.append(_add_swipe)
    gui_hooks.webview_did_receive_js_message.append(_on_message)


def _leave(mw: Any) -> None:
    mw.fullscreen = False
    mw.setWindowState(mw.windowState() & ~Qt.WindowState.WindowFullScreen)
    aqt.utils.closeTooltip()


def _add_swipe(web_content: Any, context: Any) -> None:
    if SWIPE:
        web_content.head += SWIPE_RIGHT


def _on_message(handled: tuple[bool, Any], message: str, context: Any) -> tuple[bool, Any]:
    if message != COMMAND:
        return handled
    mw = aqt.mw
    if SWIPE and mw is not None and mw.fullscreen:
        _confirm(mw)
    return (True, None)


def _confirm(mw: Any) -> None:
    """Exit Full Screen or Cancel. Shown, not exec'd: the page's message
    gets its answer at once. Application modal: open() makes it window
    modal, a sheet, which iOS shows full screen."""
    if getattr(mw, "_kioku_full_screen_box", None) is not None:
        return
    box = QMessageBox(QMessageBox.Icon.Question, "Full Screen", "Exit full screen?", parent=mw)
    exit_button = box.addButton("Exit Full Screen", QMessageBox.ButtonRole.AcceptRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(exit_button)

    def finished(_result: int) -> None:
        mw._kioku_full_screen_box = None
        if box.clickedButton() is exit_button:
            _exit(mw)
        box.deleteLater()

    box.finished.connect(finished)
    box.setWindowModality(Qt.WindowModality.ApplicationModal)
    mw._kioku_full_screen_box = box
    aqt.utils.closeTooltip()  # the hint covered the buttons
    box.show()


def _exit(mw: Any) -> None:
    if mw.fullscreen:
        _leave(mw)
        mw.show_menubar()
