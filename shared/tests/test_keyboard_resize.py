"""Android before 15: the keyboard's adjustResize shrinks Qt's available
geometry. Windows keep their size without the keyboard (kioku.windows._rest),
or their surfaces flashed black beside the editor (GitHub issue #4)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from aqt.qt import QApplication, QRect, QWidget

from kioku import windows

app = QApplication.instance() or QApplication([])

REST = QRect(0, 0, 411, 842)


@pytest.fixture
def android(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(windows.sys, "platform", "android")
    monkeypatch.setattr(windows, "_rest", QRect(REST))
    screen = {"avail": QRect(REST)}
    monkeypatch.setattr(windows, "_screen_available", lambda: QRect(screen["avail"]))
    return screen


def test_keyboard_shrink_keeps_the_rest_geometry(android) -> None:  # type: ignore[no-untyped-def]
    android["avail"] = QRect(0, 0, 411, 529)  # the keyboard took the bottom
    assert windows._keyboard_shrunk(android["avail"])
    assert windows._available() == REST


def test_other_changes_are_followed(android) -> None:  # type: ignore[no-untyped-def]
    for avail in (QRect(0, 0, 842, 411), QRect(0, 20, 411, 500), QRect(0, 0, 411, 900)):
        android["avail"] = avail
        assert not windows._keyboard_shrunk(avail)
        assert windows._available() == avail


def test_fill_is_not_the_available_geometry(android) -> None:  # type: ignore[no-untyped-def]
    # Qt resizes maximized windows, and windows exactly as large as the
    # available geometry, along with it
    w = QWidget()
    w.show()
    windows._fill(w, REST)
    assert w.geometry() != REST
    assert w.geometry().adjusted(0, 0, 0, -1) == REST
    assert windows._overhang(w) == 1
    handle = w.windowHandle()
    assert handle is not None and not handle.windowStates() & windows.Qt.WindowState.WindowMaximized
    w.close()
