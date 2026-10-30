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
