"""Preferences › Hide top bar / Hide bottom bar during review on a touch
screen.

Anki shows the hidden bars again when the mouse pointer leaves the card and
hides them a moment after it comes back. A finger never does either, so
with Hide bottom bar the answer buttons (Show Answer, Again…Easy) were gone
for good. Here a plain tap on the card (not on a link, button or field, and
not one that scrolls or selects) shows the hidden bars, and the next tap
hides them; answering a card hides them again, as the pointer coming back
over the card does on desktop.
"""

from __future__ import annotations

from typing import Any

import aqt
from aqt import gui_hooks

COMMAND = "kioku:tap-card"

# Only listens, so the card sees its touches as before
TAP_CARD = r"""
<script>
(function () {
    var start = null, moved = false;
    var ACTIVE = "a,button,input,textarea,select,label,summary,audio,video,"
        + "[onclick],[contenteditable=''],[contenteditable=true],[role=button]";
    document.addEventListener("touchstart", function (e) {
        var t = e.touches[0];
        moved = false;
        start = e.touches.length === 1 ? [t.clientX, t.clientY, Date.now()] : null;
    }, {passive: true, capture: true});
    document.addEventListener("scroll", function () { moved = true; },
        {passive: true, capture: true});
    document.addEventListener("touchend", function (e) {
        if (!start || e.touches.length) return;
        var t = e.changedTouches[0];
        var near = Math.abs(t.clientX - start[0]) < 10 && Math.abs(t.clientY - start[1]) < 10;
        var quick = Date.now() - start[2] < 500;
        start = null;
        var target = e.target && e.target.closest ? e.target : null;
        if (near && quick && !moved && !String(window.getSelection())
                && !(target && target.closest(ACTIVE))) {
            pycmd("%s");
        }
    }, {passive: true, capture: true});
})();
</script>
""" % COMMAND


def apply() -> None:
    gui_hooks.webview_will_set_content.append(_add_tap)
    gui_hooks.webview_did_receive_js_message.append(_on_message)
    gui_hooks.reviewer_did_answer_card.append(lambda *_: _hide())


def _hiding(mw: Any) -> bool:
    return mw.state == "review" and (mw.pm.hide_top_bar() or mw.pm.hide_bottom_bar())


def _add_tap(web_content: Any, context: Any) -> None:
    from aqt.reviewer import Reviewer

    if isinstance(context, Reviewer):
        web_content.head += TAP_CARD


def _on_message(handled: tuple[bool, Any], message: str, context: Any) -> tuple[bool, Any]:
    if message != COMMAND:
        return handled
    mw = aqt.mw
    if mw is not None and _hiding(mw):
        bars = (mw.toolbarWeb, mw.bottomWeb)
        if any(getattr(bar, "hidden", False) for bar in bars):
            for bar in bars:
                bar.hide_timer.stop()
                bar.show()
        else:
            _hide()
    return (True, None)


def _hide() -> None:
    """Anki's own rule: each bar hides only if its preference says so
    (and, in the Full screen mode, only in full screen)."""
    mw = aqt.mw
    if mw is None or not _hiding(mw):
        return
    for bar in (mw.toolbarWeb, mw.bottomWeb):
        bar.hide_timer.stop()
        bar.hide_if_allowed()
