"""Android: keeps a sync with AnkiWeb going while Kioku is in the background.

A few seconds after an app leaves the foreground Android cuts its network. A
sync then failed with "error sending request for url ()"; when that was the
first download, the profile stayed empty, as if the account had no decks. A
foreground service (KiokuAnkiWebService) exempts the app while a sync runs,
and while other network work holds it (hold(): kioku.packs downloads).
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
        if title:
            platform.ankiweb_sync_running(wanted, title)
        else:
            platform.ankiweb_sync_running(wanted)


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


def install() -> None:
    gui_hooks.sync_will_start.append(lambda: _on_collection(True))
    gui_hooks.sync_did_finish.append(lambda: _on_collection(False))
    gui_hooks.media_sync_did_start_or_stop.append(_on_media)
