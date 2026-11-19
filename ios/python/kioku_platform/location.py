"""Keeps Kioku running in the background, for add-ons that serve other apps
(AnkiConnect): iOS suspends an app about 5 s after it leaves the
foreground, and a suspended app answers no requests.

An app that receives location updates keeps running, so while the option
in Preferences › Advanced is on, Kioku asks for location updates at the
lowest accuracy. The locations are not used. iOS shows the location
indicator while Kioku runs in the background."""

from __future__ import annotations

import logging

from rubicon.objc import NSObject, ObjCClass, objc_method
from rubicon.objc.runtime import load_library

from .webview import prop

logger = logging.getLogger("kioku.location")

# CLAuthorizationStatus
NOT_DETERMINED, RESTRICTED, DENIED, ALWAYS, WHEN_IN_USE = range(5)
# kCLLocationAccuracyThreeKilometers: cell towers and Wi-Fi, no GPS
THREE_KILOMETERS = 3000.0

_manager = None
_delegate = None
_wanted = False


class KiokuLocationDelegate(NSObject):
    @objc_method
    def locationManagerDidChangeAuthorization_(self, manager) -> None:
        _update()

    @objc_method
    def locationManager_didUpdateLocations_(self, manager, locations) -> None:
        pass

    @objc_method
    def locationManager_didFailWithError_(self, manager, error) -> None:
        logger.info("location: %s", error)


def keep_running(on: bool) -> None:
    global _manager, _delegate, _wanted
    _wanted = on
    if _manager is None:
        if not on:
            return
        load_library("CoreLocation")
        _delegate = KiokuLocationDelegate.alloc().init()
        _manager = ObjCClass("CLLocationManager").alloc().init()
        _manager.setDesiredAccuracy_(THREE_KILOMETERS)
        _manager.setDistanceFilter_(THREE_KILOMETERS)
        # the delegate reports the authorization at once, which calls _update
        _manager.setDelegate_(_delegate)
    _update()


def status() -> str:
    """"off", "asking", "denied" or "on"."""
    if not _wanted or _manager is None:
        return "off"
    auth = int(prop(_manager, "authorizationStatus"))
    if auth == NOT_DETERMINED:
        return "asking"
    if auth in (RESTRICTED, DENIED):
        return "denied"
    return "on"


def _update() -> None:
    m = _manager
    if m is None:
        return
    auth = int(prop(m, "authorizationStatus"))
    if _wanted and auth == NOT_DETERMINED:
        m.requestWhenInUseAuthorization()
    elif _wanted and auth in (ALWAYS, WHEN_IN_USE):
        # without auto-pause: iOS would pause updates (and suspend Kioku)
        # once the phone stays in one place
        m.setPausesLocationUpdatesAutomatically_(False)
        m.setAllowsBackgroundLocationUpdates_(True)
        m.setShowsBackgroundLocationIndicator_(True)
        m.startUpdatingLocation()
        logger.info("keeping Kioku running in the background")
    else:
        m.stopUpdatingLocation()
        m.setAllowsBackgroundLocationUpdates_(False)
