"""Anki's menus in the iPadOS menu bar.

iPadOS 26 gives every app a system menu bar (swipe down from the top of the
screen, or move the pointer there), which showed Kioku's own File, Edit,
Format, View, Window and Help above Anki's menu row, and the system's did
nothing for Anki. Qt 6.11 has no native menu bar on iOS, so this fills the
system menu bar from the Qt menu bar of the front window (the main window,
or the browser). Anki's menu row stays: the system's bar only shows on
demand, so without the row the menus would be out of sight:

- Anki's File, Edit, View and Help take the places of the system's (Edit
  keeps the system's Cut, Copy, Paste and text items, which text fields in
  pages use, but not Find); its other menus (Tools; the browser's Notes,
  Cards, Go) follow in Anki's order. Format goes, Window stays.
- The system's Undo and Redo go in any case: they undo through UIKit's undo
  manager, where Qt's text responder leaves actions aimed at itself (see
  keys.py), and Anki's Undo takes Cmd-Z instead.
- Shortcuts with Cmd, Ctrl or Option (and function keys) show in the menus
  and are UIKit key commands, which run the menu row. Shortcuts of a single
  key (D, A, /) are not: as key commands they would take the letters from
  text fields, so they stay with Qt and the menus don't show them.
- Rows follow the Qt actions when a menu opens (enabled, checked, title);
  the menus are rebuilt when actions come and go, and when the front window
  changes. A menu that fills itself on aboutToShow (the Edit menu's More
  while reviewing) is filled when the menus are built.
- The rows of a window are enabled only while that window is in front, so a
  dialog over it (the Add window, a message box) keeps its keys.

Only on iPads with the iPadOS 26 menu bar (UIMainMenuSystem), and on a Mac
running the iPad app.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import c_bool, c_char_p, c_void_p
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QGuiApplication, QKeySequence
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QMenuBar
from rubicon.objc import SEL, Block, ObjCClass, ObjCInstance, at
from rubicon.objc.runtime import objc_id

from .webview import prop

logger = logging.getLogger("kioku.menubar")

_objc = ctypes.CDLL("/usr/lib/libobjc.dylib")
_objc.objc_getClass.restype = c_void_p
_objc.objc_getClass.argtypes = [c_char_p]
_objc.sel_registerName.restype = c_void_p
_objc.sel_registerName.argtypes = [c_char_p]
_objc.class_getInstanceMethod.restype = c_void_p
_objc.class_getInstanceMethod.argtypes = [c_void_p, c_void_p]
_objc.method_getImplementation.restype = c_void_p
_objc.method_getImplementation.argtypes = [c_void_p]
_objc.method_setImplementation.restype = c_void_p
_objc.method_setImplementation.argtypes = [c_void_p, c_void_p]
_objc.class_addMethod.restype = c_bool
_objc.class_addMethod.argtypes = [c_void_p, c_void_p, c_void_p, c_char_p]

# -[UIResponder canPerformAction:withSender:]
_CAN_PERFORM = ctypes.CFUNCTYPE(c_bool, c_void_p, c_void_p, c_void_p, c_void_p)
# -[UIResponder validateCommand:], and the rows' action
_VOID_ID = ctypes.CFUNCTYPE(None, c_void_p, c_void_p, c_void_p)

ACTION = "kiokuMenuRow:"
ID_PREFIX = "io.ankidesk.kioku.menu."
# the rows' propertyList
ROW_PREFIX = "kioku-row-"

# UIKeyModifierFlags
SHIFT = 1 << 17
CONTROL = 1 << 18
OPTION = 1 << 19
COMMAND = 1 << 20
# UIMenuOptions, UIMenuElementState, UIMenuElementAttributes
DISPLAY_INLINE = 1
STATE_OFF, STATE_ON = 0, 1
ATTRIBUTE_DISABLED = 1
# UIMenuSystemElementGroupPreference
REMOVED = 1

# Anki's menus that take the place of the system's, by object name
ROLES = {"menuCol": "file", "menuEdit": "edit", "menuqt_accel_view": "view", "menuHelp": "help", "menu_Help": "help"}

_EVENTS = (QEvent.Type.ActionAdded, QEvent.Type.ActionChanged, QEvent.Type.ActionRemoved)
_WINDOW_TYPES = (Qt.WindowType.Window, Qt.WindowType.Dialog, Qt.WindowType.Sheet)


def available() -> bool:
    """An iPad (or the iPad app on a Mac) with the iPadOS 26 menu bar."""
    if not _objc.objc_getClass(b"UIMainMenuSystem"):
        return False
    return int(prop(prop(ObjCClass("UIDevice"), "currentDevice"), "userInterfaceIdiom")) == 1


_uikit: Any = None


def _const(name: str) -> str:
    """A UIKit string constant (UIMenuFile, UIKeyInputF1)."""
    global _uikit
    if _uikit is None:
        _uikit = ctypes.CDLL("/System/Library/Frameworks/UIKit.framework/UIKit")
    return str(ObjCInstance(c_void_p.in_dll(_uikit, name)))


def _plain(text: str) -> str:
    """A Qt action's text as a menu row: no mnemonics, no tab and shortcut."""
    text = text.split("\t", 1)[0]
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&")


_special_keys: dict[int, str] = {}


def _key_input(key: int) -> str | None:
    if 0x21 <= key <= 0x7E:
        return chr(key).lower()
    if not _special_keys:
        K = Qt.Key
        for n in range(1, 13):
            _special_keys[getattr(K, f"Key_F{n}").value] = _const(f"UIKeyInputF{n}")
        for qt_key, name in (
            (K.Key_Up, "UIKeyInputUpArrow"),
            (K.Key_Down, "UIKeyInputDownArrow"),
            (K.Key_Left, "UIKeyInputLeftArrow"),
            (K.Key_Right, "UIKeyInputRightArrow"),
            (K.Key_Escape, "UIKeyInputEscape"),
            (K.Key_PageUp, "UIKeyInputPageUp"),
            (K.Key_PageDown, "UIKeyInputPageDown"),
            (K.Key_Home, "UIKeyInputHome"),
            (K.Key_End, "UIKeyInputEnd"),
            (K.Key_Delete, "UIKeyInputDelete"),
        ):
            _special_keys[qt_key.value] = _const(name)
        _special_keys.update(
            {
                K.Key_Backspace.value: "\b",
                K.Key_Return.value: "\r",
                K.Key_Enter.value: "\r",
                K.Key_Tab.value: "\t",
                K.Key_Space.value: " ",
            }
        )
    return _special_keys.get(key)


def _is_function_key(key: int) -> bool:
    return Qt.Key.Key_F1.value <= key <= Qt.Key.Key_F12.value


def _key_command(action: Any) -> tuple[str, int] | None:
    """(input, modifier flags) of the action's shortcut, when it can be a key
    command: it has Cmd, Ctrl or Option, or is a function key."""
    if action.shortcutContext() == Qt.ShortcutContext.WidgetShortcut:
        return None  # not meant to work from the menu bar (patches.py)
    shortcut = action.shortcut()
    if shortcut.isEmpty() or shortcut.count() != 1:
        return None
    combo = shortcut[0]
    key = combo.key().value
    mods = combo.keyboardModifiers()
    M = Qt.KeyboardModifier
    flags = 0
    # Qt on Apple platforms: Ctrl is Command, Meta is Control
    if mods & M.ControlModifier:
        flags |= COMMAND
    if mods & M.MetaModifier:
        flags |= CONTROL
    if mods & M.AltModifier:
        flags |= OPTION
    if mods & M.ShiftModifier:
        flags |= SHIFT
    if not flags & (COMMAND | CONTROL | OPTION) and not _is_function_key(key):
        return None
    text = _key_input(key)
    if text is None:
        return None
    return text, flags


def _main_window_of(window: Any) -> Any:
    """The QWidget top-level for a QWindow."""
    for w in QApplication.topLevelWidgets():
        if w.windowHandle() is window:
            return w
    return None


def _menu_bar(window: Any) -> Any:
    if isinstance(window, QMainWindow) and not sip.isdeleted(window):
        bar = window.menuWidget()
        if isinstance(bar, QMenuBar) and bar.actions():
            return bar
    return None


class MenuBar(QObject):
    def __init__(self, mw: Any) -> None:
        super().__init__(mw)
        self.mw = mw
        self.front: Any = mw
        self.owner: Any = mw
        self.rows: dict[str, Any] = {}  # propertyList key -> QAction
        self.building = False
        self.hooks: list[Any] = []
        self.watched: set[int] = set()
        self.UICommand = ObjCClass("UICommand")
        self.UIKeyCommand = ObjCClass("UIKeyCommand")
        self.UIMenu = ObjCClass("UIMenu")
        self.ids = {
            name: _const(f"UIMenu{name}")
            for name in ("Root", "Application", "File", "Edit", "View", "Window", "Help", "Format", "UndoRedo")
        }
        self._rebuild_pending = False
        self._add_responder_methods()
        self.system = prop(ObjCClass("UIMainMenuSystem"), "sharedSystem")
        config = ObjCClass("UIMainMenuSystemConfiguration").alloc().init()
        config.setTextFormattingPreference_(REMOVED)
        # Qt's text fields and the pages have no UIKit find; the browser's
        # Cmd-F and Cmd-G are Anki's
        config.setFindingPreference_(REMOVED)
        self.build_block = Block(self._build, None, objc_id)
        self.system.setBuildConfiguration_buildHandler_(config, self.build_block)
        QGuiApplication.instance().focusWindowChanged.connect(self._focus_changed)
        # menus that fill themselves on aboutToShow follow the screen (the
        # Edit menu's More: the card on show)
        from aqt import gui_hooks

        for hook in (
            gui_hooks.state_did_change,
            gui_hooks.reviewer_did_show_question,
            gui_hooks.reviewer_did_show_answer,
        ):
            hook.append(lambda *_: self.rebuild())
        self.rebuild()

    # Qt side

    def _focus_changed(self, window: Any) -> None:
        if window is None or window.type() not in _WINDOW_TYPES:
            return  # a page took the focus (keys.py), or a popup
        widget = _main_window_of(window)
        if widget is None or widget is self.front:
            return
        self.front = widget
        owner = widget if _menu_bar(widget) is not None else self.owner
        if _menu_bar(owner) is None or sip.isdeleted(owner) or not owner.isVisible():
            owner = self.mw
        if owner is not self.owner:
            self.owner = owner
            if owner is not self.mw:
                owner.installEventFilter(self)
            self.rebuild()

    def _front(self) -> Any:
        front = self.front
        if front is None or sip.isdeleted(front) or not front.isVisible():
            return self.mw
        return front

    def eventFilter(self, obj: Any, event: Any) -> bool:
        kind = event.type()
        if kind in _EVENTS:
            if not self.building and isinstance(obj, (QMenu, QMenuBar)):
                self.rebuild()
        elif kind == QEvent.Type.Hide and obj is self.owner and obj is not self.mw:
            # the browser closed: back to the main window's menus
            self.owner = self.mw
            self.rebuild()
        return False

    def _watch(self, menu: Any) -> None:
        if id(menu) not in self.watched:
            self.watched.add(id(menu))
            menu.installEventFilter(self)
            menu.destroyed.connect(lambda _=None, k=id(menu): self.watched.discard(k))

    def rebuild(self) -> None:
        if not self._rebuild_pending:
            self._rebuild_pending = True
            QTimer.singleShot(0, self._set_needs_rebuild)

    def _set_needs_rebuild(self) -> None:
        self._rebuild_pending = False
        self.system.setNeedsRebuild()

    # UIKit side

    def _add_responder_methods(self) -> None:
        """The rows' action, and their validation, on UIApplication: the end
        of every responder chain."""
        app = _objc.objc_getClass(b"UIApplication")

        def add(name: str, kind: Any, handler: Any, types: bytes) -> Any:
            sel = _objc.sel_registerName(name.encode())
            inherited = _objc.class_getInstanceMethod(app, sel)
            original = kind(_objc.method_getImplementation(inherited)) if inherited else None
            hook = kind(handler)
            self.hooks.append(hook)
            if not _objc.class_addMethod(app, sel, ctypes.cast(hook, c_void_p), types):
                _objc.method_setImplementation(
                    _objc.class_getInstanceMethod(app, sel), ctypes.cast(hook, c_void_p)
                )
            return original

        self.action_sel = _objc.sel_registerName(ACTION.encode())
        add(ACTION, _VOID_ID, self._perform, b"v@:@")
        self.can_perform = add("canPerformAction:withSender:", _CAN_PERFORM, self._can_perform, b"B@::@")
        self.validate = add("validateCommand:", _VOID_ID, self._validate, b"v@:@")

    def _key(self, command: int) -> str | None:
        key = ObjCInstance(c_void_p(command)).propertyList
        if key is None or not key.isKindOfClass_(ObjCClass("NSString")):
            return None
        key = str(key)
        return key if key.startswith(ROW_PREFIX) else None

    def _row(self, command: int) -> Any:
        action = self.rows.get(self._key(command) or "")
        if action is None or sip.isdeleted(action):
            return None
        return action

    def _enabled(self, action: Any) -> bool:
        if not action.isEnabled() or not action.isVisible():
            return False
        # the rows of a window work only while it is in front
        if QApplication.activeModalWidget() is not None:
            return False
        return self._front() is self.owner

    def _perform(self, app: int, cmd: int, sender: int) -> None:
        try:
            action = self._row(sender)
            if action is not None and self._enabled(action):
                # out of UIKit's callback: the row may open a modal dialog
                QTimer.singleShot(0, action.trigger)
        except Exception:
            logger.exception("menu row")

    def _can_perform(self, app: int, cmd: int, sel: int, sender: int) -> bool:
        if sel == self.action_sel:
            try:
                action = self._row(sender) if sender else None
                return action is not None and self._enabled(action)
            except Exception:
                logger.exception("menu row state")
                return False
        return bool(self.can_perform and self.can_perform(app, cmd, sel, sender))

    def _validate(self, app: int, cmd: int, command: int) -> None:
        try:
            if self._key(command) is not None:
                instance = ObjCInstance(c_void_p(command))
                action = self._row(command)
                if action is not None:
                    instance.setTitle_(_plain(action.text()))
                    on = action.isCheckable() and action.isChecked()
                    instance.setState_(STATE_ON if on else STATE_OFF)
                    instance.setAttributes_(0 if self._enabled(action) else ATTRIBUTE_DISABLED)
                return
        except Exception:
            logger.exception("menu row validation")
        if self.validate:
            self.validate(app, cmd, command)

    def _build(self, builder_ptr: Any) -> None:
        self.building = True
        try:
            self._build_menus(ObjCInstance(builder_ptr))
        except Exception:
            logger.exception("menu bar")
        finally:
            self.building = False

    def _build_menus(self, builder: Any) -> None:
        ids = self.ids
        owner = self.owner
        if sip.isdeleted(owner) or not owner.isVisible():
            owner = self.owner = self.mw
        bar = _menu_bar(owner)
        self.rows = {}
        self.taken: set[tuple[str, int]] = set()
        # the system's Undo and Redo always go (see above)
        builder.removeMenuForIdentifier_(at(ids["UndoRedo"]))
        builder.removeMenuForIdentifier_(at(ids["Format"]))
        for name in ("Application", "Edit", "Window"):
            self._collect_keys(builder.menuForIdentifier_(at(ids[name])))
        if bar is None:
            return
        self._watch(bar)
        placed: set[str] = set()
        previous = ids["File"]
        for n, top in enumerate(bar.actions()):
            menu = top.menu()
            if menu is None or not top.isVisible():
                continue
            role = ROLES.get(menu.objectName())
            children = self._children(menu)
            title = at(_plain(menu.title()))
            if role == "edit":
                # before the system's Cut, Copy, Paste
                group = self.UIMenu.menuWithTitle_image_identifier_options_children_(
                    at(""), None, at(ID_PREFIX + "edit"), DISPLAY_INLINE, children
                )
                builder.insertChildMenu_atStartOfMenuForIdentifier_(group, at(ids["Edit"]))
                previous = ids["Edit"]
            elif role is not None:
                ident = ids[role.capitalize()]
                new = self.UIMenu.menuWithTitle_image_identifier_options_children_(
                    title, None, at(ident), 0, children
                )
                builder.replaceMenuForIdentifier_withMenu_(at(ident), new)
                previous = ident
            else:
                ident = f"{ID_PREFIX}{n}"
                new = self.UIMenu.menuWithTitle_image_identifier_options_children_(
                    title, None, at(ident), 0, children
                )
                builder.insertSiblingMenu_afterMenuForIdentifier_(new, at(previous))
                previous = ident
            if role is not None:
                placed.add(role)
        # the system's own File, View and Help do nothing for Anki
        for role in ("file", "view", "help"):
            if role not in placed:
                builder.removeMenuForIdentifier_(at(ids[role.capitalize()]))

    def _collect_keys(self, menu: Any) -> None:
        """Key commands already in the menus: a second one with the same
        keys would be ambiguous."""
        if menu is None:
            return
        for child in menu.children:
            if child.isKindOfClass_(self.UIMenu):
                self._collect_keys(child)
            elif child.isKindOfClass_(self.UIKeyCommand):
                text = child.input
                if text is not None:
                    self.taken.add((str(text).lower(), int(child.modifierFlags) & ~(1 << 16)))

    def _children(self, menu: Any) -> Any:
        """A Qt menu's rows; separators start inline groups."""
        self._watch(menu)
        # as if it opened (receivers() can't tell for menus made in C++)
        menu.aboutToShow.emit()
        try:
            return self._groups(menu)
        finally:
            menu.aboutToHide.emit()

    def _groups(self, menu: Any) -> Any:
        groups: list[tuple[str, list[Any]]] = [("", [])]
        for action in menu.actions():
            if not action.isVisible():
                continue
            if action.isSeparator():
                groups.append((_plain(action.text()), []))
                continue
            element = self._element(action)
            if element is not None:
                groups[-1][1].append(element)
        groups = [g for g in groups if g[1]]
        if len(groups) == 1 and not groups[0][0]:
            return groups[0][1]
        return [
            self.UIMenu.menuWithTitle_image_identifier_options_children_(
                at(title), None, None, DISPLAY_INLINE, elements
            )
            for title, elements in groups
        ]

    def _element(self, action: Any) -> Any:
        submenu = action.menu()
        if submenu is not None:
            children = self._children(submenu)
            if not children:
                return None
            return self.UIMenu.menuWithTitle_image_identifier_options_children_(
                at(_plain(submenu.title() or action.text())), None, None, 0, children
            )
        key = f"{ROW_PREFIX}{len(self.rows)}"
        self.rows[key] = action
        title = at(_plain(action.text()))
        shortcut = _key_command(action)
        if shortcut is not None and shortcut not in self.taken:
            self.taken.add(shortcut)
            return self.UIKeyCommand.commandWithTitle_image_action_input_modifierFlags_propertyList_(
                title, None, SEL(ACTION), at(shortcut[0]), shortcut[1], at(key)
            )
        return self.UICommand.commandWithTitle_image_action_propertyList_(title, None, SEL(ACTION), at(key))


_menu_bar_instance: MenuBar | None = None


def install(mw: Any) -> bool:
    """Called once the main window exists. False where the system has no
    menu bar to fill."""
    global _menu_bar_instance
    if _menu_bar_instance is not None:
        return True
    try:
        if not available():
            return False
        _menu_bar_instance = MenuBar(mw)
    except Exception:
        logger.exception("menu bar")
        return False
    return True

