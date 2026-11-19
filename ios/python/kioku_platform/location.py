"""Keeps Kioku running in the background, for add-ons that serve other apps
(AnkiConnect): iOS suspends an app about 5 s after it leaves the
foreground, and a suspended app answers no requests.

An app that receives location updates keeps running, so while the option
in Preferences › Advanced is on, Kioku asks for location updates at the
lowest accuracy. The locations are not used. iOS shows the location
arrow when Kioku goes to the background (with approximate location it can
disappear later; Kioku keeps running, screen locked too).

Location access belongs to the whole app, add-ons and web pages included.
install_guard() (at start-up, before add-ons load) lets only Kioku's own
CLLocationManager ask for access or start updates, and makes `location`
nil for every manager. Add-ons run in Kioku's process, so a determined
one can undo this; the guard stops add-ons and pages that simply use the
API. Info.plist's NSLocationDefaultAccuracyReduced makes iOS grant
approximate location unless the user turns Precise on."""

from __future__ import annotations

import logging
from ctypes import CFUNCTYPE, c_void_p, cast
from typing import Any

from rubicon.objc import NSObject, ObjCClass, objc_method
from rubicon.objc.runtime import IMP, SEL, libobjc, load_library

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
        pass  # only the updates keep Kioku running; the locations are ignored

    @objc_method
    def locationManager_didFailWithError_(self, manager, error) -> None:
        logger.info("location: %s", error)


def _ensure_manager() -> Any:
    global _manager, _delegate
    if _manager is None:
        load_library("CoreLocation")
        _delegate = KiokuLocationDelegate.alloc().init()
        _manager = ObjCClass("CLLocationManager").alloc().init()
        _manager.setDesiredAccuracy_(THREE_KILOMETERS)
        _manager.setDistanceFilter_(THREE_KILOMETERS)
        # the delegate reports the authorization at once, which calls _update
        _manager.setDelegate_(_delegate)
    return _manager


def keep_running(on: bool) -> None:
    global _wanted
    _wanted = on
    if _manager is None and not on:
        return
    _ensure_manager()
    _update()


def status() -> str:
    """"off", "allowed" (off, but iOS still allows Kioku location access),
    "asking", "denied" or "on"."""
    auth = int(prop(_ensure_manager(), "authorizationStatus"))
    if not _wanted:
        return "allowed" if auth in (ALWAYS, WHEN_IN_USE) else "off"
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


# --- only Kioku's own manager --------------------------------------------------

_VOID0 = CFUNCTYPE(None, c_void_p, c_void_p)
_VOID1 = CFUNCTYPE(None, c_void_p, c_void_p, c_void_p)
_VOID2 = CFUNCTYPE(None, c_void_p, c_void_p, c_void_p, c_void_p)
_ID0 = CFUNCTYPE(c_void_p, c_void_p, c_void_p)

# CLLocationManager methods that ask for access or deliver locations
GUARDED = {
    "requestWhenInUseAuthorization": _VOID0,
    "requestAlwaysAuthorization": _VOID0,
    "requestTemporaryFullAccuracyAuthorizationWithPurposeKey:": _VOID1,
    "requestTemporaryFullAccuracyAuthorizationWithPurposeKey:completion:": _VOID2,
    "startUpdatingLocation": _VOID0,
    "requestLocation": _VOID0,
    "startMonitoringSignificantLocationChanges": _VOID0,
    "startMonitoringVisits": _VOID0,
    "startMonitoringForRegion:": _VOID1,
    "startRangingBeaconsSatisfyingConstraint:": _VOID1,
    "setDelegate:": _VOID1,
}

_callbacks: list[Any] = []  # the replacement IMPs, kept alive
_blocked: set[str] = set()


def _ptr(obj: Any) -> int | None:
    return None if obj is None else obj.ptr.value


def allowed(manager: int | None, name: str, args: tuple = ()) -> bool:
    """Whether CLLocationManager `manager` may run method `name`."""
    ours = manager is not None and manager == _ptr(_manager)
    if name == "setDelegate:":
        # Kioku's manager keeps Kioku's delegate; others may set theirs,
        # they never receive locations
        return not ours or (bool(args) and args[0] == _ptr(_delegate))
    if name.startswith("requestTemporaryFullAccuracy"):
        return False
    return ours


def install_guard() -> None:
    if _callbacks:
        return
    load_library("CoreLocation")
    cls = ObjCClass("CLLocationManager")
    for name, proto in GUARDED.items():
        method = libobjc.class_getInstanceMethod(cls.ptr, SEL(name))
        if not method:
            continue
        original = cast(libobjc.method_getImplementation(method), proto)

        def guard(manager, cmd, *args, original=original, name=name):  # type: ignore[no-untyped-def]
            if allowed(manager, name, args):
                original(manager, cmd, *args)
            elif name not in _blocked:
                _blocked.add(name)
                logger.warning("blocked CLLocationManager %s: not Kioku's own", name)

        _install(method, proto(guard))
    method = libobjc.class_getInstanceMethod(cls.ptr, SEL("location"))
    if method:
        _install(method, _ID0(lambda manager, cmd: None))
    logger.info("location guard installed")


def _install(method: Any, callback: Any) -> None:
    _callbacks.append(callback)
    libobjc.method_setImplementation(method, cast(callback, IMP))
