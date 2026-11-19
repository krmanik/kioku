"""The foreground service held during a sync with AnkiWeb (kioku.ankiwebsync):
held from the collection's sync through the media sync, released afterwards."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from aqt.qt import QApplication

import kioku_platform
from kioku import ankiwebsync

app = QApplication.instance() or QApplication([])


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    recorded: list[bool] = []
    monkeypatch.setattr(kioku_platform, "ankiweb_sync_running", recorded.append, raising=False)
    monkeypatch.setattr(ankiwebsync, "_collection", False)
    monkeypatch.setattr(ankiwebsync, "_media", False)
    monkeypatch.setattr(ankiwebsync, "_service_running", False)
    monkeypatch.setattr(ankiwebsync, "_service_title", "")
    monkeypatch.setattr(ankiwebsync, "_holders", {})
    # stop at once instead of through the timer
    monkeypatch.setattr(
        ankiwebsync.QTimer, "singleShot", lambda _ms, callback: callback(), raising=False
    )
    return recorded


def test_held_through_collection_and_media(calls: list[bool]) -> None:
    ankiwebsync._on_collection(True)
    ankiwebsync._on_media(True)
    ankiwebsync._on_collection(False)
    assert calls == [True]
    ankiwebsync._on_media(False)
    assert calls == [True, False]


def test_released_when_the_sync_fails_without_media(calls: list[bool]) -> None:
    ankiwebsync._on_collection(True)
    ankiwebsync._on_collection(False)
    assert calls == [True, False]


def test_media_only_sync(calls: list[bool]) -> None:
    ankiwebsync._on_media(True)
    ankiwebsync._on_media(False)
    assert calls == [True, False]


def test_held_for_a_download(calls: list[bool], monkeypatch: pytest.MonkeyPatch) -> None:
    titles: list[tuple[bool, str]] = []
    monkeypatch.setattr(kioku_platform, "ankiweb_sync_running",
                        lambda running, title="": titles.append((running, title)))
    ankiwebsync.hold("packs", True)
    ankiwebsync._on_collection(True)
    ankiwebsync._on_collection(False)
    ankiwebsync.hold("packs", False)
    title = ankiwebsync.HOLD_TITLES["packs"]
    assert titles == [(True, title), (True, ""), (True, title), (False, "")]


# Media sync resumed after network errors
######################################################################


class _FakeSyncer:
    def __init__(self) -> None:
        self.starts: list[bool] = []
        self.progress: list[str] = []
        self.syncing = False

    def is_syncing(self) -> bool:
        return self.syncing

    def start(self, is_periodic_sync: bool = False) -> None:
        self.starts.append(is_periodic_sync)

    def _update_progress(self, text: str) -> None:
        self.progress.append(text)


class _FakeMw:
    def __init__(self) -> None:
        self.col = object()
        self.media_syncer = _FakeSyncer()


@pytest.fixture
def resume(monkeypatch: pytest.MonkeyPatch, calls: list[bool]):  # type: ignore[no-untyped-def]
    import aqt
    import aqt.utils

    r = ankiwebsync._Resume()
    monkeypatch.setattr(ankiwebsync, "_resume", r)
    mw = _FakeMw()
    monkeypatch.setattr(aqt, "mw", mw, raising=False)
    tips: list[str] = []
    monkeypatch.setattr(aqt.utils, "tooltip", lambda msg, **kw: tips.append(msg))
    scheduled: list[int] = []
    monkeypatch.setattr(r, "_schedule", scheduled.append)
    monkeypatch.setattr(ankiwebsync, "_badge", lambda count: None)
    return r, mw, tips, scheduled


def test_network_error_is_retried_then_shown(resume) -> None:  # type: ignore[no-untyped-def]
    from anki.errors import NetworkError

    r, mw, tips, scheduled = resume
    err = NetworkError("Connection timed out.", None, None, None)
    handled = [r.on_network_error(err) for _ in range(len(ankiwebsync.RETRY_DELAYS_MS) + 1)]
    assert handled == [True] * len(ankiwebsync.RETRY_DELAYS_MS) + [False]
    assert scheduled == list(ankiwebsync.RETRY_DELAYS_MS)
    assert tips == [ankiwebsync.INTERRUPTED_TIP]  # once, not on every retry
    assert r.pending


def test_retry_starts_a_quiet_media_sync(resume) -> None:  # type: ignore[no-untyped-def]
    r, mw, _tips, _scheduled = resume
    r.start()
    assert mw.media_syncer.starts == []  # nothing failed
    r.pending = True
    mw.media_syncer.syncing = True
    r.start()
    assert mw.media_syncer.starts == []  # already running
    mw.media_syncer.syncing = False
    r.start()
    assert mw.media_syncer.starts == [True]


def test_success_after_a_retry_clears_it(resume) -> None:  # type: ignore[no-untyped-def]
    from anki.errors import NetworkError

    r, _mw, _tips, _scheduled = resume
    r.on_network_error(NetworkError("x", None, None, None))
    r.on_start_stop(True)
    r.on_start_stop(False)  # no error reported after the stop: completed
    assert not r.pending and r.attempt == 0


def test_failure_after_a_retry_keeps_it(resume) -> None:  # type: ignore[no-untyped-def]
    from anki.errors import NetworkError

    r, _mw, _tips, _scheduled = resume
    r.on_network_error(NetworkError("x", None, None, None))
    r.on_start_stop(True)
    # MediaSyncer._on_finished: the stop hook, then the error
    ankiwebsync.QTimer.singleShot = lambda _ms, cb: None  # type: ignore[method-assign]
    r.on_start_stop(False)
    r.on_network_error(NetworkError("x", None, None, None))
    r._after_stop()
    assert r.pending and r.attempt == 2


def test_coming_back_retries_again(resume) -> None:  # type: ignore[no-untyped-def]
    from anki.errors import NetworkError

    r, _mw, _tips, scheduled = resume
    for _ in range(len(ankiwebsync.RETRY_DELAYS_MS) + 1):
        r.on_network_error(NetworkError("x", None, None, None))
    scheduled.clear()
    r.on_active()
    assert scheduled == [1500] and r.attempt == 0
    r.pending = False
    r.on_active()
    assert scheduled == [1500]


def test_media_syncer_error_handling(resume, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    import aqt.utils
    from anki.errors import NetworkError, SyncError, SyncErrorKind
    from aqt.mediasync import MediaSyncer

    r, mw, _tips, _scheduled = resume
    shown: list[str] = []
    monkeypatch.setattr(aqt.utils, "show_info", lambda text, **kw: shown.append(text))
    monkeypatch.setattr(MediaSyncer, "_handle_sync_error", MediaSyncer._handle_sync_error)
    import aqt.mediasync

    monkeypatch.setattr(aqt.mediasync, "show_info", lambda text, **kw: shown.append(text))
    from types import SimpleNamespace

    fake_tr = SimpleNamespace(sync_media_failed=lambda: "Media sync failed.")
    monkeypatch.setattr(aqt.utils, "tr", fake_tr)
    monkeypatch.setattr(aqt.mediasync, "tr", fake_tr)
    ankiwebsync._patch_media_syncer()
    syncer = mw.media_syncer
    for _ in ankiwebsync.RETRY_DELAYS_MS:
        MediaSyncer._handle_sync_error(syncer, NetworkError("Connection timed out.", None, None, None))
    assert shown == []
    MediaSyncer._handle_sync_error(syncer, NetworkError("Connection timed out.", None, None, None))
    assert shown == ["Connection timed out.\n\n" + ankiwebsync.GAVE_UP_TEXT]
    # a dropped download: retried too, shown without rslib's raw text
    r.attempt = 0
    dropped = SyncError('HttpError { code: 303, context: "reading stream" }', None, None, None,
                        SyncErrorKind.OTHER)
    for _ in ankiwebsync.RETRY_DELAYS_MS:
        MediaSyncer._handle_sync_error(syncer, dropped)
    assert len(shown) == 1
    MediaSyncer._handle_sync_error(syncer, dropped)
    assert shown[-1] == ankiwebsync.CONNECTION_LOST + "\n\n" + ankiwebsync.GAVE_UP_TEXT
    # a failed login as before
    MediaSyncer._handle_sync_error(syncer, SyncError("auth", None, None, None, SyncErrorKind.AUTH))
    assert shown[-1] == "auth"


@pytest.mark.parametrize("text, count", [
    ("Added: ⁨0⁩↑ ⁨72⁩↓, Removed: ⁨0⁩↑ ⁨0⁩↓", 72),
    ("Added: 0↑ 5↓", 5),
    ("Media sync complete.", None),
])
def test_badge_count_from_progress(text: str, count: int | None, monkeypatch: pytest.MonkeyPatch) -> None:
    badges: list[int | None] = []
    monkeypatch.setattr(ankiwebsync, "_badge", badges.append)
    monkeypatch.setattr(ankiwebsync, "_resume", ankiwebsync._Resume())
    ankiwebsync._on_media_progress(text)
    assert badges == ([count] if count is not None else [])


def test_ios_renews_the_background_task_on_return(calls: list[bool], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ankiwebsync.sys, "platform", "ios")
    ankiwebsync._renew()
    assert calls == []  # no sync running
    ankiwebsync._on_collection(True)
    ankiwebsync._renew()
    assert calls == [True, True]
    monkeypatch.setattr(ankiwebsync.sys, "platform", "android")
    ankiwebsync._renew()
    assert calls == [True, True]


def test_error_of_the_last_retry_is_shown(resume, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """Kioku's retries start the media sync as a periodic one (no box per
    retry); once they run out the error is shown all the same. Anki's own
    periodic sync stays quiet."""
    import aqt.mediasync
    import aqt.utils
    from types import SimpleNamespace

    from anki.errors import NetworkError
    from aqt.mediasync import MediaSyncer

    r, mw, _tips, _scheduled = resume
    shown: list[str] = []
    monkeypatch.setattr(aqt.utils, "show_info", lambda text, **kw: shown.append(text))
    monkeypatch.setattr(aqt.mediasync, "show_info", lambda text, **kw: shown.append(text))
    fake_tr = SimpleNamespace(sync_media_failed=lambda: "Media sync failed.")
    monkeypatch.setattr(aqt.utils, "tr", fake_tr)
    monkeypatch.setattr(aqt.mediasync, "tr", fake_tr)
    monkeypatch.setattr(MediaSyncer, "_handle_sync_error", MediaSyncer._handle_sync_error)
    ankiwebsync._patch_media_syncer()
    syncer = mw.media_syncer
    err = NetworkError("A network error occurred.", None, None, None)
    MediaSyncer._handle_sync_error(syncer, err)  # the user's sync: retry 1
    for _ in ankiwebsync.RETRY_DELAYS_MS:
        r.start()  # a retry, as periodic
        assert syncer.starts[-1] is True
        MediaSyncer._handle_sync_error(syncer, err, True)
    assert shown == ["A network error occurred.\n\n" + ankiwebsync.GAVE_UP_TEXT]
    # Anki's own periodic media sync, retries used up: quiet as before
    MediaSyncer._handle_sync_error(syncer, err, True)
    assert len(shown) == 1
