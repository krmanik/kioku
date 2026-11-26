"""Safe mode: Anki without add-ons, for when an add-on keeps Kioku from
starting (GitHub issue #32).

Ways in:

- After a start that didn't finish (the app closed or crashed before the
  profile was open for a few seconds), the next start asks whether to start
  without add-ons. That start's log is kept as kioku-previous.log.
- The app icon's quick action (iOS: touch and hold, Android: app shortcut)
  "Start in Safe Mode" leaves a request (REQUEST in Documents, written by
  the native side). Taken at the next start; while Kioku is running, it
  offers to close Kioku so it starts in safe mode when opened again.
- The web version: ?safe=1 in the address (the platform's
  safe_mode_requested()), or the link on the loading page. It has no start
  marker.
- KIOKU_SAFE_MODE=1 in the environment (tests).

Safe mode is Anki's own (--safemode): add-ons aren't loaded, and there's
no automatic sync. Tools › Add-ons still lists every add-on, so the broken
one can be turned off there. The deck list says that safe mode is on.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

logger = logging.getLogger("kioku.safemode")

# in Documents; the native quick actions write REQUEST too
STARTING = ".kioku-starting"
REQUEST = ".kioku-safe-mode"
PREVIOUS_LOG = "kioku-previous.log"
# a start counts as finished this long after the profile opened
SETTLE_MS = 5000
COMMAND = "kioku:safe-mode"

_documents = ""
_crashed = False
_requested = False


def _path(name: str) -> str:
    return os.path.join(_documents, name)


def keep_previous_log(documents: str, log_path: str) -> None:
    """Before the log is started anew: keep the log of a start that didn't
    finish."""
    if os.path.exists(os.path.join(documents, STARTING)) and os.path.exists(log_path):
        try:
            os.replace(log_path, os.path.join(documents, PREVIOUS_LOG))
        except OSError:
            pass


def begin(documents: str) -> None:
    """At start, before aqt.run(): decide what to ask and mark the start."""
    global _documents, _crashed, _requested
    _documents = documents
    _crashed = os.path.exists(_path(STARTING))
    _requested = _take_request() or os.environ.get("KIOKU_SAFE_MODE") == "1"
    try:
        import kioku_platform

        asked = getattr(kioku_platform, "safe_mode_requested", None)
        if asked is not None and asked():
            _requested = True
    except Exception:
        logger.exception("safe mode request")
    if sys.platform != "emscripten":
        # (the web version saves its files now and then, and a tab is
        # closed without Kioku closing: a marker could outlive good starts)
        try:
            with open(_path(STARTING), "w"):
                pass
        except OSError:
            logger.exception("start marker")
    if _crashed:
        print("Kioku: the last start did not finish")
    if _requested:
        print("Kioku: safe mode requested")
        # Anki's AnkiApp decides from its arguments
        if "--safemode" not in sys.argv:
            sys.argv.append("--safemode")
    _patch_main_window()


def _take_request() -> bool:
    try:
        os.remove(_path(REQUEST))
        return True
    except OSError:
        return False


def finished() -> None:
    """The start went well (or Kioku closes normally)."""
    try:
        os.remove(_path(STARTING))
    except OSError:
        pass


def _has_addons(pm: Any) -> bool:
    try:
        folder = pm.addonFolder()
        return any(
            not name.startswith((".", "_")) and os.path.isdir(os.path.join(folder, name))
            for name in os.listdir(folder)
        )
    except Exception:
        return False


def _ask_after_crash() -> bool:
    from aqt.qt import QMessageBox

    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Kioku")
    box.setText(
        "Kioku closed while starting last time.\n\n"
        "If an add-on caused it, start without add-ons (safe mode) and turn "
        "the add-on off in Tools › Add-ons.\n\n"
        f"The log of that start is {PREVIOUS_LOG} in Kioku's files."
    )
    safe = box.addButton("Start Without Add-ons", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Start Normally", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(safe)
    box.exec()
    return box.clickedButton() is safe


def _patch_main_window() -> None:
    import aqt.main

    from aqt import gui_hooks

    init = aqt.main.AnkiQt.__init__

    def __init__(self, app, profileManager, backend, opts, args):  # type: ignore[no-untyped-def]
        # the app has decided from its arguments (Shift held, --safemode);
        # the main window takes app.safeMode
        if not getattr(app, "safeMode", False) and not getattr(opts, "safemode", False):
            if _requested:
                safe = True
            elif _crashed and _has_addons(profileManager):
                try:
                    safe = _ask_after_crash()
                except Exception:
                    logger.exception("safe mode question")
                    safe = False
            else:
                safe = False
            if safe:
                opts.safemode = True
                if app is not None:
                    app.safeMode = True
        if getattr(app, "safeMode", False) or getattr(opts, "safemode", False):
            # before the profile opens and the deck list is first drawn
            gui_hooks.deck_browser_will_render_content.append(_banner)
            gui_hooks.webview_did_receive_js_message.append(_on_js_message)
        init(self, app, profileManager, backend, opts, args)

    aqt.main.AnkiQt.__init__ = __init__
    # (the main window opens the profile before main_window_did_init)
    gui_hooks.profile_did_open.append(_profile_opened)
    gui_hooks.main_window_did_init.append(_main_window_ready)


def _profile_opened() -> None:
    from aqt.qt import QTimer

    QTimer.singleShot(SETTLE_MS, finished)


def _main_window_ready() -> None:
    import aqt
    from aqt import gui_hooks
    from aqt.qt import QGuiApplication, QTimer, Qt

    mw = aqt.mw
    app = QGuiApplication.instance()
    app.applicationStateChanged.connect(
        lambda state: _request_while_running() if state == Qt.ApplicationState.ApplicationActive else None
    )
    if not mw.safeMode:
        return
    # Anki's own tooltip blames the Shift key
    from aqt.utils import tooltip

    QTimer.singleShot(0, lambda: tooltip("Safe mode: add-ons are off", period=5000))


BANNER = """<div id="kioku-safe-mode" style="margin:8px auto 12px;max-width:480px;padding:8px 12px;
border-radius:8px;background:rgba(255,170,0,.18);border:1px solid rgba(255,170,0,.6);font-size:15px">
<b>Safe mode:</b> add-ons are off.
<a href="#" onclick="pycmd('%s');return false;">What now?</a></div>""" % COMMAND


def _banner(deck_browser: Any, content: Any) -> None:
    content.tree = BANNER + content.tree


def _on_js_message(handled: tuple[bool, Any], message: str, context: Any) -> tuple[bool, Any]:
    if message != COMMAND:
        return handled
    from aqt.qt import QTimer

    QTimer.singleShot(0, _explain)
    return (True, None)


def _restart_hint() -> str:
    if sys.platform == "ios":
        return "close Kioku (swipe it up in the app switcher) and open it again"
    if sys.platform == "android":
        return "close Kioku (swipe it away in Recents) and open it again"
    return "reload the page"


def _explain() -> None:
    import aqt
    from aqt.qt import QMessageBox

    box = QMessageBox(aqt.mw)
    box.setWindowTitle("Safe mode")
    box.setText(
        "Kioku started without add-ons, and without syncing automatically.\n\n"
        "Turn off the add-on that caused the problem in Tools › Add-ons, "
        f"then {_restart_hint()} to load the others."
    )
    addons = box.addButton("Add-ons…", QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Close)
    box.exec()
    if box.clickedButton() is addons:
        # Tools › Add-ons, whatever Anki calls its handler
        aqt.mw.form.actionAdd_ons.trigger()


def _request_while_running() -> None:
    """The quick action while Kioku runs: it has to start again for it."""
    import aqt
    from aqt.qt import QMessageBox, QTimer

    mw = aqt.mw
    if not _documents or mw is None:
        return

    def ask() -> None:
        # iOS can hand over the quick action after the app is active. Shown
        # over any window open then: an add-on's (invisible) modal box would
        # otherwise hold it back
        if not os.path.exists(_path(REQUEST)):
            return
        if mw.safeMode:
            _take_request()
            return
        box = QMessageBox(mw)
        box.setWindowTitle("Safe mode")
        box.setText(
            "Kioku is already running with its add-ons. To start without them, "
            "Kioku has to close first; it starts in safe mode when you open it again."
        )
        close = box.addButton("Close Kioku", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is close:
            mw.close()  # the request stays for the next start
        else:
            _take_request()

    QTimer.singleShot(1000, ask)
