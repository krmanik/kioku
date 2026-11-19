"""A Done bar above the iPhone's number pad.

Qt shows the number pad for number fields (spin boxes such as Custom Study's
"Increase today's new card limit by"). It has no Return key, and the window's
own buttons (OK) sat under it: nothing closed the keyboard, so the dialog
could not be finished. A bar with Done above such keyboards closes the
keyboard, which leaves the entered number in the field (as leaving it does)
and uncovers the buttons. Qt takes the bar as the input accessory view
through the field's ImPlatformData. iPad keyboards have keys to close them
and are left alone.
"""

from __future__ import annotations

import logging
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QWidget
from rubicon.objc import SEL, NSObject, ObjCClass, objc_method

from .webview import prop

logger = logging.getLogger("kioku.donebar")

UIToolbar = ObjCClass("UIToolbar")
UIBarButtonItem = ObjCClass("UIBarButtonItem")
UIDevice = ObjCClass("UIDevice")
NSArray = ObjCClass("NSArray")

# UIBarButtonSystemItem
FLEXIBLE_SPACE = 5
DONE = 0
# UIViewAutoresizing
FLEXIBLE_WIDTH = 1 << 1
FLEXIBLE_HEIGHT = 1 << 4
# UIUserInterfaceIdiom
IDIOM_PHONE = 0
# qiosinputcontext.h kImePlatformDataInputAccessoryView
ACCESSORY_KEY = "inputAccessoryView"

H = Qt.InputMethodHint
# keyboards without a Return key (qiostextresponder.mm picks the number pad
# or phone pad for these, unless the field takes URLs or e-mail addresses)
PAD_HINTS = H.ImhDigitsOnly | H.ImhDialableCharactersOnly
OTHER_KEYBOARDS = H.ImhUrlCharactersOnly | H.ImhEmailCharactersOnly


class KiokuDoneTarget(NSObject):
    @objc_method
    def done_(self, sender) -> None:  # type: ignore[no-untyped-def]
        # resigns Qt's text responder, which also clears the focus
        im = QGuiApplication.inputMethod()
        if im is not None:
            im.hide()


def _hints(obj: QObject) -> int:
    query = getattr(obj, "inputMethodQuery", None)
    if query is None:
        return 0
    value = query(Qt.InputMethodQuery.ImHints)
    try:
        return int(getattr(value, "value", value) or 0)
    except (TypeError, ValueError):
        return 0


def needs_bar(hints: int) -> bool:
    return bool(hints & PAD_HINTS.value) and not hints & OTHER_KEYBOARDS.value


class DoneBarFilter(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._target = KiokuDoneTarget.alloc().init()
        bar = UIToolbar.alloc().init()
        bar.setAutoresizingMask_(FLEXIBLE_WIDTH | FLEXIBLE_HEIGHT)
        space = UIBarButtonItem.alloc().initWithBarButtonSystemItem_target_action_(
            FLEXIBLE_SPACE, None, None
        )
        done = UIBarButtonItem.alloc().initWithBarButtonSystemItem_target_action_(
            DONE, self._target, SEL("done:")
        )
        bar.setItems_(NSArray.arrayWithArray_([space, done]))
        bar.sizeToFit()
        self._bar = bar

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if (
            event is None
            or event.type() != QEvent.Type.InputMethodQuery
            or not isinstance(obj, QWidget)
            or not event.queries() & Qt.InputMethodQuery.ImPlatformData  # type: ignore[attr-defined]
        ):
            return False
        if not needs_bar(_hints(obj)):
            return False
        # answer the query as QWidget::event does (protected in PyQt for
        # widgets Qt created), with the bar added to the platform data
        queries = event.queries().value  # type: ignore[attr-defined]
        for bit in range(32):
            if not queries & (1 << bit):
                continue
            query = Qt.InputMethodQuery(1 << bit)
            value = obj.inputMethodQuery(query)
            if query == Qt.InputMethodQuery.ImEnabled and value is None and obj.isEnabled():
                value = True
            if query == Qt.InputMethodQuery.ImPlatformData:
                value = dict(value) if isinstance(value, dict) else {}
                value[ACCESSORY_KEY] = sip.voidptr(self._bar.ptr.value)
            event.setValue(query, value)  # type: ignore[attr-defined]
        event.accept()
        return True


_filter: DoneBarFilter | None = None


def install(app: QApplication) -> None:
    global _filter
    if _filter is not None:
        return
    try:
        if prop(prop(UIDevice, "currentDevice"), "userInterfaceIdiom") != IDIOM_PHONE:
            return
        _filter = DoneBarFilter(app)
        app.installEventFilter(_filter)
    except Exception:
        logger.exception("done bar")
