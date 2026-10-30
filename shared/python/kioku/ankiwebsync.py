"""Android: keeps a sync with AnkiWeb going while Kioku is in the background.

A few seconds after an app leaves the foreground Android cuts its network. A
sync then failed with "error sending request for url ()"; when that was the
first download, the profile stayed empty, as if the account had no decks. A
foreground service (KiokuAnkiWebService) exempts the app while a sync runs.
"""

from __future__ import annotations

from aqt import gui_hooks
from aqt.qt import QTimer

import kioku_platform as platform

# a sync that fails at once, or the media sync that follows the collection's,
# should not flicker the notification; and Android does not allow stopping the
# service before it has reached the foreground
STOP_DELAY_MS = 1000

_collection = False
_media = False
_service_running = False


def _apply() -> None:
    global _service_running
    wanted = _collection or _media
    if wanted != _service_running:
        _service_running = wanted
        platform.ankiweb_sync_running(wanted)


def _changed() -> None:
    if _collection or _media:
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


def install() -> None:
    gui_hooks.sync_will_start.append(lambda: _on_collection(True))
    gui_hooks.sync_did_finish.append(lambda: _on_collection(False))
    gui_hooks.media_sync_did_start_or_stop.append(_on_media)
