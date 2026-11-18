"""Game controllers through Apple's GameController framework, for
kioku.gamepad.

Every controller with the extended profile (Xbox, PlayStation, Switch Pro,
8BitDo and other MFi controllers) reports its changes to one handler on the
main queue, Qt's thread; it tells the listener which button went down or up
and where the sticks and triggers are. Apple names buttons by position (A
is the bottom one), as kioku.gamepad does.

Web pages don't use the Web Gamepad API in Kioku; WebKit's old crash with
an app that also uses GameController (WebKit bug 247368) was fixed in 2022.
"""

from __future__ import annotations

import ctypes
import logging
from typing import Any

from rubicon.objc import Block, ObjCClass, ObjCInstance, at
from rubicon.objc.runtime import load_library, objc_id, send_message

from .webview import prop

logger = logging.getLogger("kioku.gamepad")

CONNECT = "GCControllerDidConnectNotification"
DISCONNECT = "GCControllerDidDisconnectNotification"

# kioku.gamepad's name -> GCExtendedGamepad property
BUTTONS = {
    "A": "buttonA",
    "B": "buttonB",
    "X": "buttonX",
    "Y": "buttonY",
    "L1": "leftShoulder",
    "R1": "rightShoulder",
    "Menu": "buttonMenu",
    "View": "buttonOptions",  # nil on controllers without one
    "L3": "leftThumbstickButton",
    "R3": "rightThumbstickButton",
}
DPAD = {"Up": "up", "Down": "down", "Left": "left", "Right": "right"}

_listener: Any = None
_observers: list[Any] = []
_blocks: list[Any] = []  # blocks UIKit holds must stay alive
_pads: dict[int, "_Pad"] = {}  # controller address -> pad


def _address(value: Any) -> int:
    if isinstance(value, ObjCInstance):
        return int(value.ptr.value or 0)
    return int(getattr(value, "value", value) or 0)


def _pressed(button: Any) -> bool:
    return bool(send_message(button, "isPressed", restype=ctypes.c_bool, argtypes=[]))


def _value(axis: Any) -> float:
    return float(send_message(axis, "value", restype=ctypes.c_float, argtypes=[]))


class _Pad:
    """One controller and the elements whose changes are reported."""

    def __init__(self, controller: Any) -> None:
        self.controller = controller
        self.id = str(_address(controller))
        self.name = str(prop(controller, "vendorName") or "Game controller")
        self.pad = prop(controller, "extendedGamepad")
        # element address -> what to read when it changes
        self.elements: dict[int, Any] = {}
        if self.pad is None:
            return
        for name, getter in BUTTONS.items():
            element = prop(self.pad, getter)
            if element is not None:
                self.elements[_address(element)] = ("button", name, element)
        dpad = prop(self.pad, "dpad")
        self.elements[_address(dpad)] = (
            "dpad",
            None,
            {name: prop(dpad, getter) for name, getter in DPAD.items()},
        )
        for stick in ("left", "right"):
            element = prop(self.pad, stick + "Thumbstick")
            axes = (prop(element, "xAxis"), prop(element, "yAxis"))
            self.elements[_address(element)] = ("stick", stick, axes)
        triggers = (prop(self.pad, "leftTrigger"), prop(self.pad, "rightTrigger"))
        for trigger in triggers:
            self.elements[_address(trigger)] = ("triggers", None, triggers)
        self.block = Block(self._changed, None, objc_id, objc_id)
        _blocks.append(self.block)
        send_message(
            self.pad, "setValueChangedHandler:", self.block, restype=None, argtypes=[objc_id]
        )

    def _changed(self, pad: Any, element: Any) -> None:
        try:
            entry = self.elements.get(_address(element))
            if entry is None or _listener is None:
                return
            kind, name, what = entry
            if kind == "button":
                _listener.button(name, _pressed(what), "pad:" + self.id)
            elif kind == "dpad":
                for direction, button in what.items():
                    _listener.button(direction, _pressed(button), "dpad:" + self.id)
            elif kind == "stick":
                # GameController's y is up; kioku.gamepad's is down
                _listener.axes(name, _value(what[0]), -_value(what[1]))
            elif kind == "triggers":
                _listener.axes("triggers", _value(what[0]), _value(what[1]))
        except Exception:
            logger.exception("gamepad input")

    def close(self) -> None:
        if self.pad is not None:
            send_message(
                self.pad, "setValueChangedHandler:", None, restype=None, argtypes=[objc_id]
            )


def _connect(controller: Any) -> None:
    key = _address(controller)
    if _listener is None or key in _pads:
        return
    pad = _Pad(controller)
    if pad.pad is None:
        logger.info("%s has no extended gamepad profile: ignored", pad.name)
        return
    _pads[key] = pad
    if _listener is not None:
        _listener.connected(pad.id, pad.name, True)


def _disconnect(controller: Any) -> None:
    pad = _pads.pop(_address(controller), None)
    if pad is None:
        return
    pad.close()
    if _listener is not None:
        _listener.connected(pad.id, pad.name, False)


def _on_note(handler: Any) -> Any:
    def note(notification: Any) -> None:
        try:
            handler(prop(ObjCInstance(objc_id(_address(notification))), "object"))
        except Exception:
            logger.exception("gamepad connection")

    return note


def watch(listener: Any) -> None:
    """kioku.gamepad's listener, or None to stop."""
    global _listener
    _listener = listener
    if listener is None:
        for pad in list(_pads.values()):
            pad.close()
        _pads.clear()
        return
    load_library("GameController")
    if not _observers:
        center = prop(ObjCClass("NSNotificationCenter"), "defaultCenter")
        queue = prop(ObjCClass("NSOperationQueue"), "mainQueue")
        for name, handler in ((CONNECT, _connect), (DISCONNECT, _disconnect)):
            block = Block(_on_note(handler), None, objc_id)
            _blocks.append(block)
            _observers.append(
                center.addObserverForName_object_queue_usingBlock_(at(name), None, queue, block)
            )
    for controller in prop(ObjCClass("GCController"), "controllers") or []:
        _connect(controller)
