"""Keeps a sync with AnkiWeb going on phones, above all the download of
pictures and sounds (the media sync), which runs after the cards' sync and
can take a long time with big decks.

Android: a few seconds after an app leaves the foreground Android cuts its
network. A sync then failed with "error sending request for url ()"; when that
was the first download, the profile stayed empty, as if the account had no
decks. A foreground service (KiokuAnkiWebService) exempts the app while a sync
runs, and while other network work holds it (hold(): kioku.packs downloads).

iOS: an app is suspended about 5 s after it leaves the foreground or the
screen locks. A background task gets a sync some more time, and the screen
stays on while one runs in the foreground.

Both: when the media sync still fails on a network error (the connection
dropped while the app was suspended, say), Anki showed "Connection timed out"
or a raw "HttpError { code: 303, ... }" and stopped: the cards were all there, most pictures were missing, and
nothing resumed the download until the next manual sync, or a silent periodic
one after 15 minutes. Here it starts again by itself a few times, and again
whenever Kioku comes back to the foreground, until it completes. While it
runs, the Sync button shows how many files came down.
"""

from __future__ import annotations

import logging
import re
import sys

from aqt import gui_hooks
from aqt.qt import QTimer

import kioku_platform as platform

logger = logging.getLogger("kioku.ankiwebsync")

# a sync that fails at once, or the media sync that follows the collection's,
# should not flicker the notification; and Android does not allow stopping the
# service before it has reached the foreground
STOP_DELAY_MS = 1000

# media sync retries after a network error, then again on every return to
# the foreground
RETRY_DELAYS_MS = (5_000, 30_000, 120_000)

INTERRUPTED_TIP = (
    "Downloading pictures and sounds was interrupted. Kioku continues by itself."
)
GAVE_UP_TEXT = (
    "Some pictures and sounds are not downloaded yet. Kioku continues when you "
    "come back to it, or tap Sync."
)

CONNECTION_LOST = "The connection was lost."

_collection = False
_media = False
_service_running = False
_service_title = ""
# other work that needs the network -> its notification's title
_holders: dict[str, str] = {}

HOLD_TITLES = {"packs": "Downloading extra files for add-ons"}


def _apply() -> None:
    global _service_running, _service_title
    syncing = _collection or _media
    wanted = syncing or bool(_holders)
    title = "" if syncing or not wanted else next(iter(_holders.values()))
    if (wanted, title) != (_service_running, _service_title):
        _service_running, _service_title = wanted, title
        running = getattr(platform, "ankiweb_sync_running", None)
        if running is None:
            return
        if title:
            running(wanted, title)
        else:
            running(wanted)


def _renew() -> None:
    """iOS: a background task that ran out ends while the sync goes on; on
    the next return to the foreground start another, so the next trip to
    the background gets time again (the call is idempotent there)."""
    if sys.platform == "ios" and _service_running:
        running = getattr(platform, "ankiweb_sync_running", None)
        if running is not None:
            running(True)


def hold(name: str, on: bool) -> None:
    """Keep the service, and with it the network, while name's work runs."""
    if on:
        _holders[name] = HOLD_TITLES.get(name, "Kioku is downloading")
    else:
        _holders.pop(name, None)
    _changed()


def _changed() -> None:
    if _collection or _media or _holders:
        _apply()
    else:
        QTimer.singleShot(STOP_DELAY_MS, _apply)


def _on_collection(running: bool) -> None:
    global _collection
    _collection = running
    _changed()


def _on_media(running: bool) -> None:
    global _media
    _media = running
    _changed()
    _resume.on_start_stop(running)


# Media sync: resume after network errors
######################################################################


class _Resume:
    def __init__(self) -> None:
        # the last media sync ended on a network error and hasn't completed since
        self.pending = False
        self.failed = False
        self.attempt = 0
        self.downloaded = -1
        self.timer: QTimer | None = None
        # the running media sync was started by start(): Anki treats it as
        # periodic and would not show its error
        self.retrying = False

    def on_start_stop(self, running: bool) -> None:
        if running:
            self.failed = False
            self.downloaded = -1
            return
        _badge(None)
        # MediaSyncer._on_finished reports an error right after this hook
        QTimer.singleShot(0, self._after_stop)

    def _after_stop(self) -> None:
        if not self.failed and self.pending:
            logger.info("media sync completed after an interruption")
            self.pending = False
            self.attempt = 0
        if not self.failed:
            self.retrying = False

    def on_network_error(self, exc: BaseException) -> bool:
        """True if the error was taken care of (a retry follows), False to
        show it. Called on the main thread."""
        import aqt

        self.failed = True
        first = not self.pending
        self.pending = True
        if self.attempt < len(RETRY_DELAYS_MS):
            delay = RETRY_DELAYS_MS[self.attempt]
            self.attempt += 1
            logger.warning("media sync failed (%s); retry %d in %d ms", exc, self.attempt, delay)
            self._schedule(delay)
            if first and aqt.mw is not None:
                from aqt.utils import tooltip

                tooltip(INTERRUPTED_TIP, period=5000, parent=aqt.mw)
            return True
        logger.warning("media sync failed (%s); waiting for the app to come back", exc)
        return False

    def _schedule(self, delay: int) -> None:
        if self.timer is None:
            self.timer = QTimer()
            self.timer.setSingleShot(True)
            self.timer.timeout.connect(self.start)
        self.timer.start(delay)

    def start(self) -> None:
        import aqt

        mw = aqt.mw
        if mw is None or mw.col is None or not self.pending:
            return
        if mw.media_syncer.is_syncing():
            return
        logger.info("resuming media sync")
        # periodic: no "Media sync failed" box from Anki for each retry;
        # handle_sync_error shows the error once the retries run out
        self.retrying = True
        mw.media_syncer.start(is_periodic_sync=True)

    def on_active(self) -> None:
        if self.pending:
            self.attempt = 0
            if self.timer is not None:
                self.timer.stop()
            # the network may need a moment after the phone wakes up
            self._schedule(1500)

    def on_profile_closed(self) -> None:
        self.pending = self.failed = self.retrying = False
        self.attempt = 0
        if self.timer is not None:
            self.timer.stop()


_resume = _Resume()


def _retryable(exc: BaseException) -> bool:
    """A network error, or the connection dropping while a file downloads
    (rslib reports that as a sync error of kind Other, with the raw text
    "HttpError { code: 303, context: \"reading stream\" ... }"). Not a
    failed login, nor an error unrelated to the network."""
    from anki.errors import NetworkError, SyncError, SyncErrorKind

    if isinstance(exc, NetworkError):
        return True
    return isinstance(exc, SyncError) and exc.kind == SyncErrorKind.OTHER


def _message(exc: BaseException) -> str:
    text = str(exc)
    return CONNECTION_LOST if text.startswith("HttpError") else text


def _patch_media_syncer() -> None:
    from aqt.mediasync import MediaSyncer

    original = MediaSyncer._handle_sync_error

    def handle_sync_error(self, exc, is_periodic_sync=False):  # type: ignore[no-untyped-def]
        if _retryable(exc):
            if _resume.on_network_error(exc):
                from aqt.utils import tr

                self._update_progress(tr.sync_media_failed())
                return
            if not is_periodic_sync or _resume.retrying:
                _resume.retrying = False
                from aqt.qt import Qt
                from aqt.utils import show_info, tr

                self._update_progress(tr.sync_media_failed())
                show_info(f"{_message(exc)}\n\n{GAVE_UP_TEXT}", modality=Qt.WindowModality.NonModal)
                return
        original(self, exc, is_periodic_sync)

    MediaSyncer._handle_sync_error = handle_sync_error


# Sync button: files downloaded so far
######################################################################

# "Added: ⁨0⁩↑ ⁨72⁩↓" (Fluent wraps numbers in isolation marks)
_DOWN = re.compile(r"(\d+)[⁨⁩]*\s*↓")

_BADGE_JS = """(() => {
  const sync = document.getElementById('sync');
  if (!sync) return;
  let b = document.getElementById('kioku-media-count');
  const text = %s;
  if (!text) { if (b) b.remove(); return; }
  if (!b) {
    b = document.createElement('span');
    b.id = 'kioku-media-count';
    // the toolbar clips what overflows it (overflow: hidden, 31 px tall):
    // top right corner of the Sync item, over the spinner's corner
    b.style.cssText = 'position:absolute;right:0;top:1px;font-size:9px;font-weight:600;' +
      'line-height:1;padding:1px 3px;border-radius:6px;pointer-events:none;' +
      'background:var(--accent-card, #3a7bd5);color:#fff';
    if (getComputedStyle(sync).position === 'static') sync.style.position = 'relative';
    sync.appendChild(b);
  }
  b.textContent = text;
})()"""


def _badge(count: int | None) -> None:
    import json

    import aqt

    mw = aqt.mw
    if mw is None or getattr(mw, "toolbar", None) is None:
        return
    text = f"↓{count}" if count else ""
    mw.toolbar.web.eval(_BADGE_JS % json.dumps(text))


def _on_media_progress(progress: str) -> None:
    m = _DOWN.search(progress)
    if m is None:
        return
    count = int(m.group(1))
    if count != _resume.downloaded:
        _resume.downloaded = count
        _badge(count)


def _on_toolbar_redraw(*_args: object) -> None:
    import aqt

    if aqt.mw is not None and aqt.mw.media_syncer.is_syncing() and _resume.downloaded > 0:
        _badge(_resume.downloaded)


def _watch_app_state() -> None:
    from aqt.qt import QGuiApplication, Qt

    app = QGuiApplication.instance()
    if app is None:
        return

    def on_state(state: Qt.ApplicationState) -> None:
        if state == Qt.ApplicationState.ApplicationActive:
            _renew()
            _resume.on_active()

    app.applicationStateChanged.connect(on_state)


def install() -> None:
    gui_hooks.sync_will_start.append(lambda: _on_collection(True))
    gui_hooks.sync_did_finish.append(lambda: _on_collection(False))
    gui_hooks.media_sync_did_start_or_stop.append(_on_media)
    gui_hooks.media_sync_did_progress.append(_on_media_progress)
    gui_hooks.top_toolbar_did_redraw.append(_on_toolbar_redraw)
    gui_hooks.profile_will_close.append(_resume.on_profile_closed)
    gui_hooks.main_window_did_init.append(_watch_app_state)
    _patch_media_syncer()
    logger.debug("installed on %s", sys.platform)
