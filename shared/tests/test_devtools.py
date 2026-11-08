"""The dev command channel runs Documents/.kioku-cmd.py, so a file that shows
up in the app's (user-visible) Documents folder must not turn it on in a
build that is not a development build."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


@pytest.fixture
def devtools(platform, monkeypatch):
    from kioku import devtools

    documents = platform.documents_dir()
    os.makedirs(documents)
    monkeypatch.setattr(devtools, "DOCUMENTS", documents)
    monkeypatch.setattr(devtools, "_timer", None)
    monkeypatch.delenv("KIOKU_DEV", raising=False)
    monkeypatch.setattr(platform, "keep_awake", lambda: None, raising=False)
    yield devtools
    if devtools._timer is not None:
        devtools._timer.stop()
    qInstallMessageHandler(None)


def touch_marker(devtools) -> None:
    open(os.path.join(devtools.DOCUMENTS, ".kioku-dev"), "w").close()


def test_marker_file_is_ignored_in_a_release_build(devtools, platform, monkeypatch) -> None:
    touch_marker(devtools)
    monkeypatch.setattr(platform, "dev_allowed", lambda: False, raising=False)
    devtools.install()
    assert devtools._timer is None


def test_marker_file_is_ignored_when_the_platform_has_no_dev_build(devtools) -> None:
    touch_marker(devtools)
    devtools.install()
    assert devtools._timer is None


def test_marker_file_works_in_a_dev_build(devtools, platform, monkeypatch) -> None:
    touch_marker(devtools)
    monkeypatch.setattr(platform, "dev_allowed", lambda: True, raising=False)
    devtools.install()
    assert devtools._timer is not None and devtools._timer.isActive()


def test_environment_variable_works_in_a_dev_build(devtools, platform, monkeypatch) -> None:
    monkeypatch.setenv("KIOKU_DEV", "1")
    monkeypatch.setattr(platform, "dev_allowed", lambda: True, raising=False)
    devtools.install()
    assert devtools._timer is not None


def test_environment_variable_works_where_the_platform_has_no_dev_build(devtools, monkeypatch) -> None:
    monkeypatch.setenv("KIOKU_DEV", "1")
    devtools.install()
    assert devtools._timer is not None
