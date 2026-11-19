"""The iOS Info.plist (ios/src/Info.plist.in): privacy usage descriptions.
iOS ends an app that touches a protected resource without one."""

from __future__ import annotations

import os
import plistlib

PLIST = os.path.join(os.path.dirname(__file__), "..", "..", "ios", "src", "Info.plist.in")


def load() -> dict:
    with open(PLIST, "rb") as f:
        return plistlib.load(f)


def test_microphone_usage_description() -> None:
    # issue #19: add-ons recording through AVAudioRecorder (rubicon-objc)
    text = load().get("NSMicrophoneUsageDescription", "")
    assert isinstance(text, str) and len(text.strip()) > 20


def test_location_background_mode() -> None:
    # issue #21: kioku_platform/location.py sets allowsBackgroundLocationUpdates,
    # which raises without the "location" background mode
    plist = load()
    assert "location" in plist.get("UIBackgroundModes", [])
    text = plist.get("NSLocationWhenInUseUsageDescription", "")
    assert isinstance(text, str) and "AnkiConnect" in text


def test_location_approximate_by_default() -> None:
    # the permission is the whole app's, add-ons included
    assert load().get("NSLocationDefaultAccuracyReduced") is True
