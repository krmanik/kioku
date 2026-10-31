"""Hardware keyboard keys reach Anki's shortcuts after a page was tapped.

A tap on a page (the card, the review screen's buttons) makes the web view's
content view UIKit's first responder, and Qt then takes its window for
inactive: Qt refuses key presses without an active window, and no shortcut
of a widget matches. WebKit kept Space and Return for itself (scrolling),
so with an iPad keyboard the card never turned over. Worse, without an
active window Qt offers UIKit every shortcut as a key command named after
the shortcut's last letter (Space as "e", Return as "n"): those swallowed
letters and digits and still couldn't match.

So a key pressed outside a text field in a page makes the Qt view hosting
the page first responder again, which reactivates its window, as before the
tap, and goes to Qt; the page gets it too if Qt doesn't take it. Qt offers
no key commands while it has no active window. A text field in a page keeps
every key.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import c_bool, c_char_p, c_int, c_void_p
from typing import Any

from PyQt6.QtGui import QGuiApplication
from rubicon.objc import ObjCClass, ObjCInstance
from rubicon.objc.runtime import send_message

logger = logging.getLogger("kioku.keys")

_objc = ctypes.CDLL("/usr/lib/libobjc.dylib")
_objc.objc_getClass.restype = c_void_p
_objc.objc_getClass.argtypes = [c_char_p]
_objc.sel_registerName.restype = c_void_p
_objc.sel_registerName.argtypes = [c_char_p]
_objc.class_getInstanceMethod.restype = c_void_p
_objc.class_getInstanceMethod.argtypes = [c_void_p, c_void_p]
_objc.method_setImplementation.restype = c_void_p
_objc.method_setImplementation.argtypes = [c_void_p, c_void_p]

# -[UIResponder pressesBegan:withEvent:] and the like
_PRESSES = ctypes.CFUNCTYPE(None, c_void_p, c_void_p, c_void_p, c_void_p)
# -[UIResponder keyCommands]
_GETTER = ctypes.CFUNCTYPE(c_void_p, c_void_p, c_void_p)

# QEvent::Type
KEY_PRESS = 6
KEY_RELEASE = 7

_originals: dict[str, Any] = {}
_hooks: list[Any] = []  # the C callbacks must stay alive
# presses (UIPress addresses) that Qt took
_taken: set[int] = set()
_no_commands: Any = None


def _qt_view(view: Any) -> Any:
    """The Qt view (QUIView) hosting the web view."""
    from .webview import prop

    while view is not None:
        if view.objc_class.name.startswith("QUI"):
            return view
        view = prop(view, "superview")
    return None


def _addresses(presses: int) -> list[int]:
    return [p.ptr.value for p in ObjCInstance(c_void_p(presses)).allObjects()]


def _to_qt(view: Any, presses: int, kind: int) -> bool:
    return bool(
        send_message(
            view,
            "handlePresses:eventType:",
            c_void_p(presses),
            kind,
            restype=c_bool,
            argtypes=[c_void_p, c_int],
        )
    )


def _began(content: int, cmd: int, presses: int, event: int) -> None:
    try:
        page = ObjCInstance(c_void_p(content))
        editing = send_message(page, "isFocusingElement", restype=c_bool, argtypes=[])
        view = None if editing else _qt_view(page)
        if view is not None:
            if QGuiApplication.focusWindow() is None:
                send_message(view, "becomeFirstResponder", restype=c_bool, argtypes=[])
            if _to_qt(view, presses, KEY_PRESS):
                _taken.update(_addresses(presses))
                return
    except Exception:
        logger.exception("key press")
    _originals["pressesBegan:withEvent:"](content, cmd, presses, event)


def _ended(name: str):  # type: ignore[no-untyped-def]
    def ended(content: int, cmd: int, presses: int, event: int) -> None:
        try:
            ours = _taken.intersection(_addresses(presses))
            if ours:
                _taken.difference_update(ours)
                view = _qt_view(ObjCInstance(c_void_p(content)))
                if view is not None:
                    _to_qt(view, presses, KEY_RELEASE)
                return
        except Exception:
            logger.exception("key release")
        _originals[name](content, cmd, presses, event)

    return ended


def _changed(content: int, cmd: int, presses: int, event: int) -> None:
    try:
        if _taken.intersection(_addresses(presses)):
            return
    except Exception:
        logger.exception("key change")
    _originals["pressesChanged:withEvent:"](content, cmd, presses, event)


def _key_commands(controller: int, cmd: int) -> int | None:
    try:
        if QGuiApplication.focusWindow() is None:
            return _no_commands.ptr.value
    except Exception:
        logger.exception("key commands")
    return _originals["keyCommands"](controller, cmd)


def _replace(cls_name: bytes, name: str, kind: Any, handler: Any) -> None:
    cls = _objc.objc_getClass(cls_name)
    method = _objc.class_getInstanceMethod(cls, _objc.sel_registerName(name.encode())) if cls else None
    if not method:
        logger.warning("no %s in %s: keys may not reach Qt", name, cls_name.decode())
        return
    hook = kind(handler)
    _hooks.append(hook)
    original = _objc.method_setImplementation(method, ctypes.cast(hook, c_void_p))
    _originals[name] = kind(original)


def install() -> None:
    global _no_commands
    if _originals:
        return
    _no_commands = ObjCClass("NSArray").alloc().init()
    for name, handler in {
        "pressesBegan:withEvent:": _began,
        "pressesChanged:withEvent:": _changed,
        "pressesEnded:withEvent:": _ended("pressesEnded:withEvent:"),
        "pressesCancelled:withEvent:": _ended("pressesCancelled:withEvent:"),
    }.items():
        _replace(b"WKContentView", name, _PRESSES, handler)
    _replace(b"QIOSViewController", "keyCommands", _GETTER, _key_commands)
