"""Gamepads and game controllers (Bluetooth or USB) drive Kioku.

The platform layer (kioku_platform.watch_gamepads) reports buttons by name
(A, B, X, Y, L1, R1, L2, R2, L3, R3, Menu, View, Up, Down, Left, Right; A is
the bottom face button, as on an Xbox controller) and the sticks, triggers
and hat switch as axes.

Controls are set per action, as in AnkiDroid (Settings › Controls): each
action has the buttons bound to it, one list while studying and one for
everywhere else. While studying a binding can be for the question side,
the answer side or both. Preferences › Advanced › Gamepad › Controls…
adds a binding by pressing the button and warns when another action
already has it.

Anki's future changes: the actions go through Anki's own keyboard shortcuts
wherever Anki has one (Space, the answer keys 1–4 as set in Anki's
preferences, R, M, E, D, S, A, B, Y…), not through its private methods,
and the settings are Kioku's own (the profile manager's meta, versioned;
nothing in the collection). The deck list's highlight reads Anki's deck list
markup and does nothing if that changes. tests/test_gamepad_anki.py checks
these against the Anki release Kioku is built with.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import aqt
from aqt import gui_hooks
from aqt.qt import (
    QAbstractButton,
    QAction,
    QApplication,
    QComboBox,
    QDialog,
    QEvent,
    QKeyEvent,
    QKeySequence,
    QMessageBox,
    QShortcut,
    Qt,
    QTimer,
    QWidget,
    sip,
)

logger = logging.getLogger("kioku.gamepad")

META_KEY = "kioku_gamepad"
VERSION = 2
REVIEW = "review"
OTHER = "other"
CONTEXT_TITLES = {REVIEW: "Studying", OTHER: "Elsewhere"}

BOTH = "both"
QUESTION = "question"
ANSWER = "answer"
SIDE_LABELS = {BOTH: "both sides", QUESTION: "question", ANSWER: "answer"}

# name, short label, where it is on the controllers
BUTTONS: list[tuple[str, str, str]] = [
    ("A", "A", "bottom face button: Xbox A, PlayStation cross, Switch B"),
    ("B", "B", "right face button: Xbox B, PlayStation circle, Switch A"),
    ("X", "X", "left face button: Xbox X, PlayStation square, Switch Y"),
    ("Y", "Y", "top face button: Xbox Y, PlayStation triangle, Switch X"),
    ("Up", "D-pad ↑", "d-pad or left stick up"),
    ("Down", "D-pad ↓", "d-pad or left stick down"),
    ("Left", "D-pad ←", "d-pad or left stick left"),
    ("Right", "D-pad →", "d-pad or left stick right"),
    ("L1", "L1", "left bumper: LB, L1, L"),
    ("R1", "R1", "right bumper: RB, R1, R"),
    ("L2", "L2", "left trigger: LT, L2, ZL"),
    ("R2", "R2", "right trigger: RT, R2, ZR"),
    ("Menu", "Menu", "Menu, Start, Options, +"),
    ("View", "View", "View, Back, Select, Share, −"),
    ("L3", "L3", "left stick press"),
    ("R3", "R3", "right stick press"),
]
BUTTON_NAMES = [b[0] for b in BUTTONS]
BUTTON_LABELS = {b[0]: b[1] for b in BUTTONS}
BUTTON_HELP = {b[0]: b[2] for b in BUTTONS}


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    contexts: tuple[str, ...]
    # Anki's keyboard shortcut for it (main window), if Anki has one
    shortcut: str | None = None


_R, _O, _RO = (REVIEW,), (OTHER,), (REVIEW, OTHER)
ACTIONS: list[Action] = [
    Action("show-answer", "Show answer", _R, " "),
    Action("again", "Again", _R),  # Anki's answer keys (Preferences)
    Action("hard", "Hard", _R),
    Action("good", "Good", _R),
    Action("easy", "Easy", _R),
    Action("undo", "Undo", _RO),
    Action("replay", "Replay audio", _R, "r"),
    Action("pause-audio", "Pause audio", _R, "5"),
    Action("more", "More (review menu)", _R, "m"),
    Action("edit", "Edit note", _R, "e"),
    Action("mark", "Mark note", _R, "*"),
    Action("bury-card", "Bury card", _R, "-"),
    Action("bury-note", "Bury note", _R, "="),
    Action("suspend-card", "Suspend card", _R, "@"),
    Action("suspend-note", "Suspend note", _R, "!"),
    Action("flag-1", "Red flag", _R, "Ctrl+1"),
    Action("flag-2", "Orange flag", _R, "Ctrl+2"),
    Action("flag-3", "Green flag", _R, "Ctrl+3"),
    Action("flag-4", "Blue flag", _R, "Ctrl+4"),
    Action("card-info", "Card info", _R, "i"),
    Action("deck-options", "Deck options", _R, "o"),
    Action("replay-voice", "Replay own voice", _R, "v"),
    Action("record-voice", "Record own voice", _R, "Shift+v"),
    Action("select", "Select (open deck, study, press button)", _O),
    Action("up", "Up (move)", _O),
    Action("down", "Down (move)", _O),
    Action("left", "Left (move, collapse deck)", _O),
    Action("right", "Right (move, expand deck)", _O),
    Action("next", "Next item (Tab)", _O),
    Action("previous", "Previous item (Shift+Tab)", _O),
    Action("scroll-up", "Scroll up", _RO),
    Action("scroll-down", "Scroll down", _RO),
    Action("back", "Back (leave, close)", _RO),
    Action("decks", "Decks", _RO, "d"),
    Action("study", "Study deck", _O, "s"),
    Action("add", "Add", _RO, "a"),
    Action("browse", "Browse", _RO, "b"),
    Action("sync", "Sync", _RO, "y"),
]
ACTION_BY_ID = {a.id: a for a in ACTIONS}
ANSWER_EASE = {"again": 1, "hard": 2, "good": 3, "easy": 4}
KEY_PREFIX = "key:"  # a custom action: run this keyboard shortcut

DEFAULTS: dict[str, dict[str, list[str]]] = {
    REVIEW: {
        "show-answer": ["A@question"],
        "good": ["A@answer"],
        "again": ["B@answer"],
        "hard": ["X@answer"],
        "easy": ["Y@answer"],
        "undo": ["L1"],
        "replay": ["R1"],
        "more": ["Menu"],
        "back": ["View"],
        "scroll-up": ["Up"],
        "scroll-down": ["Down"],
    },
    OTHER: {
        "select": ["A"],
        "back": ["B", "View"],
        "sync": ["Y"],
        "up": ["Up"],
        "down": ["Down"],
        "left": ["Left"],
        "right": ["Right"],
        "previous": ["L1"],
        "next": ["R1"],
    },
}

# actions that repeat while their button is held
REPEATING = {"up", "down", "left", "right", "scroll-up", "scroll-down", "next", "previous"}
REPEAT_DELAY_MS = 400
REPEAT_INTERVAL_MS = 110
STICK_THRESHOLD = 0.5
TRIGGER_THRESHOLD = 0.5
SCROLL_DEAD_ZONE = 0.2
SCROLL_TICK_MS = 30
SCROLL_SPEED = 40  # pixels per tick at full tilt


# --- bindings and settings ---------------------------------------------------


def parse_binding(text: str) -> tuple[str, str] | None:
    """"A", "A@answer" -> (button, side); None if not a binding."""
    button, _, side = str(text).partition("@")
    side = side or BOTH
    if button not in BUTTON_NAMES or side not in SIDE_LABELS:
        return None
    return button, side


def binding(button: str, side: str = BOTH) -> str:
    return button if side == BOTH else f"{button}@{side}"


def binding_label(text: str, context: str = REVIEW) -> str:
    parsed = parse_binding(text)
    if parsed is None:
        return text
    button, side = parsed
    label = BUTTON_LABELS[button]
    if context == REVIEW and side != BOTH:
        label += f" ({SIDE_LABELS[side]})"
    return label


def overlaps(a: str, b: str) -> bool:
    """Same button on a side both bindings cover."""
    pa, pb = parse_binding(a), parse_binding(b)
    if pa is None or pb is None or pa[0] != pb[0]:
        return False
    return BOTH in (pa[1], pb[1]) or pa[1] == pb[1]


def action_label(action_id: str) -> str:
    if action_id in ACTION_BY_ID:
        return ACTION_BY_ID[action_id].label
    if action_id.startswith(KEY_PREFIX):
        return f"Shortcut {action_id[len(KEY_PREFIX):]}"
    return action_id


def _known(action_id: str, context: str) -> bool:
    if action_id.startswith(KEY_PREFIX):
        return not QKeySequence(action_id[len(KEY_PREFIX):]).isEmpty()
    action = ACTION_BY_ID.get(action_id)
    return action is not None and context in action.contexts


@dataclass
class Settings:
    """In the profile manager's meta (all profiles), under META_KEY:
    {"version": 2, "enabled": bool, "review": {action: [binding]},
    "other": {...}}. Actions a newer Kioku adds come with their defaults,
    unless the user already uses those buttons; unknown actions and
    bindings are dropped when read."""

    enabled: bool = True
    bindings: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Any) -> Settings:
        data = data if isinstance(data, dict) else {}
        settings = cls(enabled=bool(data.get("enabled", True)))
        current = data.get("version") == VERSION
        for context, defaults in DEFAULTS.items():
            saved = data.get(context) if current else None
            saved = saved if isinstance(saved, dict) else None
            result: dict[str, list[str]] = {}
            if saved is not None:
                for action_id, items in saved.items():
                    if _known(action_id, context) and isinstance(items, list):
                        result[action_id] = [b for b in map(str, items) if parse_binding(b)]
            for action_id, items in defaults.items():
                if saved is not None and action_id in saved:
                    continue
                taken = [b for bs in result.values() for b in bs]
                result[action_id] = [b for b in items if not any(overlaps(b, t) for t in taken)]
            settings.bindings[context] = result
        return settings

    def to_dict(self) -> dict:
        return {
            "version": VERSION,
            "enabled": self.enabled,
            **{c: {a: list(b) for a, b in m.items()} for c, m in self.bindings.items()},
        }

    def action_for(self, context: str, button: str, side: str) -> str:
        """The action for a press; a binding for this side wins over one for
        both sides."""
        found = ""
        for action_id, items in self.bindings.get(context, {}).items():
            for item in items:
                parsed = parse_binding(item)
                if parsed is None or parsed[0] != button:
                    continue
                if parsed[1] == side:
                    return action_id
                if parsed[1] == BOTH and not found:
                    found = action_id
        return found

    def owner(self, context: str, item: str) -> str | None:
        """The action that has a binding overlapping `item`."""
        for action_id, items in self.bindings.get(context, {}).items():
            if any(overlaps(item, other) for other in items):
                return action_id
        return None

    def add(self, context: str, action_id: str, item: str) -> None:
        """Bind `item` to the action, taking it from any other action."""
        mapping = self.bindings.setdefault(context, {})
        for other_id, items in mapping.items():
            items[:] = [b for b in items if not overlaps(b, item)]
        mapping.setdefault(action_id, []).append(item)

    def remove(self, context: str, action_id: str, item: str) -> None:
        items = self.bindings.get(context, {}).get(action_id, [])
        if item in items:
            items.remove(item)


def load_settings(meta: dict | None) -> Settings:
    return Settings.from_dict((meta or {}).get(META_KEY))


def save_settings(pm: Any, settings: Settings) -> None:
    pm.meta[META_KEY] = settings.to_dict()
    # like syncserver.save_settings: the profile list has no pm.save()
    pm.db.execute("update profiles set data = ? where name = ?", pm._pickle(pm.meta), "_global")
    pm.db.commit()


def _meta() -> dict | None:
    pm = getattr(aqt.mw, "pm", None) if aqt.mw else None
    return getattr(pm, "meta", None)


# --- what an action does where ------------------------------------------------

DECK_SCRIPT = r"""
(function (deckId, move) {
    var rows = Array.prototype.filter.call(
        document.querySelectorAll("tr.deck"), function (r) { return r.offsetParent !== null; });
    if (!rows.length) return null;
    var i = -1;
    for (var n = 0; n < rows.length; n++) if (rows[n].id === String(deckId)) i = n;
    var shown = i >= 0 && rows[i].classList.contains("kioku-pad");
    if (i < 0) {
        for (var n = 0; n < rows.length; n++) if (rows[n].classList.contains("current")) i = n;
        if (i < 0) i = 0;
    }
    var row = rows[i];
    if (shown || move === "show") {
        if (move === "up") i = Math.max(0, i - 1);
        else if (move === "down") i = Math.min(rows.length - 1, i + 1);
        else if (move === "left" || move === "right") {
            var c = row.querySelector("a.collapse");
            var collapsed = c && c.textContent.trim() === "+";
            if (c && collapsed === (move === "right")) { c.click(); return row.id; }
        } else if (move === "select") {
            var link = row.querySelector("a.deck");
            if (link) link.click();
            return row.id;
        }
    }
    Array.prototype.forEach.call(document.querySelectorAll("tr.kioku-pad"), function (r) {
        r.classList.remove("kioku-pad");
    });
    if (!document.getElementById("kioku-pad-style")) {
        var s = document.createElement("style");
        s.id = "kioku-pad-style";
        s.textContent = "tr.kioku-pad a.deck { outline: 3px solid var(--border-focus, #0a84ff); outline-offset: 3px; border-radius: 4px; }";
        (document.head || document.documentElement).appendChild(s);
    }
    row = rows[i];
    row.classList.add("kioku-pad");
    row.scrollIntoView({block: "nearest"});
    return row.id;
})(%s, %s)
"""


def _alive(w: Any) -> bool:
    return w is not None and not sip.isdeleted(w)


def _target_window() -> QWidget | None:
    """The window a button acts on: a popup (menu), a modal dialog, the
    window with the focus, another window on top of the main window
    (full screen on a phone), or the main window."""
    mw = aqt.mw
    for w in (QApplication.activePopupWidget(), QApplication.activeModalWidget()):
        if _alive(w) and w.isVisible():
            return w
    focus = QApplication.focusWidget()
    if _alive(focus) and focus.window().isVisible():
        return focus.window()
    active = QApplication.activeWindow()
    if _alive(active) and active.isVisible():
        return active
    windows = [
        w
        for w in QApplication.topLevelWidgets()
        if w is not mw
        and w.isVisible()
        and w.windowType() in (Qt.WindowType.Window, Qt.WindowType.Dialog)
        and w.width() > 1
    ]
    if windows:
        return windows[-1]
    return mw


def _send_key(target: QWidget, key: Qt.Key, modifiers: Any = Qt.KeyboardModifier.NoModifier, text: str = "") -> None:
    for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(target, QKeyEvent(kind, key, modifiers, text))


def _focus_target(window: QWidget) -> QWidget:
    focus = window.focusWidget()
    if not _alive(focus) or not focus.isVisible():
        window.focusNextChild()
        focus = window.focusWidget()
    return focus if _alive(focus) else window


def run_shortcut(window: QWidget, text: str, press_key: bool = True) -> bool:
    """Run the enabled shortcut or menu item for `text` in `window` (the
    main window's menus are its children too); else press the key, if
    `press_key`. False if nothing ran."""
    seq = QKeySequence(text)
    if seq.isEmpty():
        return False
    for shortcut in window.findChildren(QShortcut):
        parent = shortcut.parent()
        visible = not isinstance(parent, QWidget) or parent.isVisible()
        if shortcut.isEnabled() and seq in shortcut.keys() and visible:
            shortcut.activated.emit()
            return True
    for action in window.findChildren(QAction):
        if action.isEnabled() and seq in action.shortcuts():
            action.trigger()
            return True
    if not press_key:
        return False
    combo = seq[0]
    key_text = text if len(text) == 1 else ""
    _send_key(_focus_target(window), combo.key(), combo.keyboardModifiers(), key_text)
    return True


def card_side() -> str:
    """QUESTION or ANSWER while studying (Reviewer.state)."""
    state = getattr(getattr(aqt.mw, "reviewer", None), "state", None)
    return ANSWER if state == "answer" else QUESTION


def answer_key(ease: int) -> str:
    """The key Anki answers with (Preferences › Review, answer keys)."""
    pm = getattr(aqt.mw, "pm", None)
    get = getattr(pm, "get_answer_key", None)
    try:
        key = get(ease) if get else None
    except Exception:
        key = None
    return key or str(ease)


class Actions:
    """Runs an action where the user is."""

    def __init__(self) -> None:
        self.deck_id: str | None = None  # highlighted on the deck list

    def run(self, action: str) -> None:
        mw = aqt.mw
        if not action or mw is None:
            return
        window = _target_window()
        if window is None:
            return
        if action.startswith(KEY_PREFIX):
            run_shortcut(window, action[len(KEY_PREFIX):])
        elif window is not mw:
            self._in_window(window, action)
        else:
            self._in_main(action)

    # dialogs, menus and other windows
    def _in_window(self, window: QWidget, action: str) -> None:
        if isinstance(window, QMessageBox) and not window.isVisible():
            return  # shown as a native alert: answered by touch
        keys = {
            "up": Qt.Key.Key_Up,
            "down": Qt.Key.Key_Down,
            "left": Qt.Key.Key_Left,
            "right": Qt.Key.Key_Right,
            "scroll-up": Qt.Key.Key_PageUp,
            "scroll-down": Qt.Key.Key_PageDown,
        }
        popup = window.windowType() == Qt.WindowType.Popup
        if action in keys:
            _send_key(_focus_target(window), keys[action])
        elif action == "next":
            _send_key(_focus_target(window), Qt.Key.Key_Tab)
        elif action == "previous":
            _send_key(_focus_target(window), Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
        elif action == "select":
            focus = _focus_target(window)
            if popup:
                _send_key(focus, Qt.Key.Key_Return)
            elif isinstance(focus, QAbstractButton):
                focus.animateClick()
            elif isinstance(focus, QComboBox):
                focus.showPopup()
            else:
                _send_key(focus, Qt.Key.Key_Return)
        elif action == "back":
            if popup or isinstance(window, QDialog):
                _send_key(window if not popup else _focus_target(window), Qt.Key.Key_Escape)
            else:
                window.close()
        elif action == "undo":
            aqt.mw.undo()

    # the main window: Anki's shortcuts where it has them
    def _in_main(self, action: str) -> None:
        mw = aqt.mw
        state = mw.state
        if action in ANSWER_EASE:
            if state == "review":
                run_shortcut(mw, answer_key(ANSWER_EASE[action]), press_key=False)
        elif action == "show-answer":
            # Space answers Good on the answer side: only on the question
            if state == "review" and card_side() == QUESTION:
                run_shortcut(mw, " ", press_key=False)
        elif action == "undo":
            mw.undo()
        elif action == "back":
            if state == "review":
                mw.moveToState("overview")
            elif state == "overview":
                mw.moveToState("deckBrowser")
        elif action in ("scroll-up", "scroll-down"):
            self.scroll(-0.4 if action == "scroll-up" else 0.4)
        elif state == "deckBrowser" and action in ("up", "down", "left", "right", "select", "next", "previous"):
            move = {"next": "down", "previous": "up"}.get(action, action)
            self.deck(move)
        elif state == "overview" and action == "select":
            run_shortcut(mw, "s", press_key=False)
        elif action in ("up", "down") and state in ("overview", "review"):
            self.scroll(-0.4 if action == "up" else 0.4)
        elif action in ACTION_BY_ID and ACTION_BY_ID[action].shortcut:
            run_shortcut(mw, ACTION_BY_ID[action].shortcut, press_key=False)

    def scroll(self, pages: float, smooth: bool = True) -> None:
        behavior = "smooth" if smooth else "instant"
        aqt.mw.web.eval(
            f"window.scrollBy({{top: window.innerHeight * {pages}, behavior: '{behavior}'}});"
        )

    def scroll_pixels(self, pixels: int) -> None:
        aqt.mw.web.eval(f"window.scrollBy({{top: {pixels}, behavior: 'instant'}});")

    def deck(self, move: str) -> None:
        import json

        def done(deck_id: Any) -> None:
            if deck_id is not None:
                self.deck_id = str(deck_id)

        js = DECK_SCRIPT % (json.dumps(self.deck_id), json.dumps(move))
        aqt.mw.deckBrowser.web.evalWithCallback(js, done)

    def show_deck_highlight(self) -> None:
        """After the deck list is drawn again (a collapse, a refresh)."""
        if self.deck_id is not None:
            self.deck("show")


# --- buttons, sticks, repeats ---------------------------------------------------


class Gamepads:
    """Turns the platform's button and axis reports into actions."""

    def __init__(self, run: Callable[[str], None] | None = None) -> None:
        self.actions = Actions()
        self.run = run or self.actions.run
        self.settings = load_settings(_meta())
        self.controllers: dict[str, str] = {}  # id -> name
        # the Controls dialog waits for a press (press to bind)
        self.capture: Callable[[str], None] | None = None
        # (source, button) held; a button is down while any source holds it
        self._held: set[tuple[str, str]] = set()
        self._repeat_button: str | None = None
        self._repeat = QTimer()
        self._repeat.setSingleShot(True)
        self._repeat.timeout.connect(self._on_repeat)
        self._scroll_speed = 0.0
        self._scroller = QTimer()
        self._scroller.setInterval(SCROLL_TICK_MS)
        self._scroller.timeout.connect(self._on_scroll)

    def reload(self) -> None:
        self.settings = load_settings(_meta())

    def action_for(self, button: str) -> str:
        mw = aqt.mw
        window = _target_window() if mw else None
        if mw is not None and window is mw and mw.state == "review":
            return self.settings.action_for(REVIEW, button, card_side())
        return self.settings.action_for(OTHER, button, BOTH)

    # from the platform
    def connected(self, ident: str, name: str, on: bool) -> None:
        if on:
            self.controllers[ident] = name or "Gamepad"
        else:
            self.controllers.pop(ident, None)
            # buttons held on it never come up
            self._held.clear()
            self._repeat.stop()
            self._repeat_button = None
            self._scroll_speed = 0.0
            self._scroller.stop()
        if self.settings.enabled and aqt.mw is not None:
            from aqt.utils import tooltip

            tooltip(f"{name or 'Gamepad'} {'connected' if on else 'disconnected'}", period=2000)

    def button(self, name: str, pressed: bool, source: str = "button") -> None:
        if name not in BUTTON_NAMES or not (self.settings.enabled or self.capture):
            return
        was_down = self._down(name)
        if pressed:
            self._held.add((source, name))
        else:
            self._held.discard((source, name))
        is_down = self._down(name)
        if is_down and not was_down:
            self._press(name)
        elif was_down and not is_down and self._repeat_button == name:
            self._repeat.stop()
            self._repeat_button = None

    def axes(self, stick: str, x: float, y: float) -> None:
        """stick: "left", "right" (y > 0 is down), "hat" (the d-pad as
        axes), "triggers" (x: left, y: right; 0 to 1)."""
        if not (self.settings.enabled or self.capture):
            return
        if stick in ("left", "hat"):
            for name, on in (
                ("Left", x <= -STICK_THRESHOLD),
                ("Right", x >= STICK_THRESHOLD),
                ("Up", y <= -STICK_THRESHOLD),
                ("Down", y >= STICK_THRESHOLD),
            ):
                self.button(name, on, stick)
        elif stick == "triggers":
            self.button("L2", x >= TRIGGER_THRESHOLD, "trigger")
            self.button("R2", y >= TRIGGER_THRESHOLD, "trigger")
        elif stick == "right" and not self.capture:
            self._scroll_speed = 0.0 if abs(y) < SCROLL_DEAD_ZONE else y
            if self._scroll_speed and not self._scroller.isActive():
                self._scroller.start()
            elif not self._scroll_speed:
                self._scroller.stop()

    # internals
    def _down(self, name: str) -> bool:
        return any(button == name for _, button in self._held)

    def _press(self, name: str) -> None:
        if self.capture is not None:
            try:
                self.capture(name)
            except Exception:
                logger.exception("binding %s", name)
            return
        action = self.action_for(name)
        self._fire(action)
        if action in REPEATING:
            self._repeat_button = name
            self._repeat.start(REPEAT_DELAY_MS)

    def _on_repeat(self) -> None:
        name = self._repeat_button
        if name is None or not self._down(name) or self.capture is not None:
            return
        action = self.action_for(name)
        if action not in REPEATING:
            return
        self._fire(action)
        self._repeat.start(REPEAT_INTERVAL_MS)

    def _on_scroll(self) -> None:
        if not self._scroll_speed or aqt.mw is None or _target_window() is not aqt.mw:
            return
        try:
            self.actions.scroll_pixels(int(self._scroll_speed * SCROLL_SPEED))
        except Exception:
            logger.exception("scrolling")

    def _fire(self, action: str) -> None:
        if not action:
            return
        try:
            self.run(action)
        except Exception:
            logger.exception("gamepad action %s", action)


_gamepads: Gamepads | None = None


def instance() -> Gamepads | None:
    return _gamepads


def settings_changed() -> None:
    """After the Controls dialog or the Advanced tab saved."""
    if _gamepads is None:
        return
    _gamepads.reload()
    _watch(_gamepads.settings.enabled)


def _watch(on: bool) -> None:
    import kioku_platform

    watch = getattr(kioku_platform, "watch_gamepads", None)
    if watch is None:
        return
    try:
        watch(_gamepads if on else None)
    except Exception:
        logger.exception("watching gamepads")


def start() -> None:
    global _gamepads
    if _gamepads is not None:
        return
    _gamepads = Gamepads()
    gui_hooks.deck_browser_did_render.append(lambda _browser: _gamepads.actions.show_deck_highlight())
    _watch(_gamepads.settings.enabled)


def install() -> None:
    gui_hooks.main_window_did_init.append(start)


# --- Preferences › Advanced › Gamepad › Controls… -------------------------------


class ControlsDialog(QDialog):
    """Like AnkiDroid's Settings › Controls: one row per action with its
    buttons; a tap on a row adds (press the button) or removes them."""

    def __init__(self, parent: QWidget | None, pm: Any, pads: Gamepads | None = None) -> None:
        from aqt.qt import QDialogButtonBox, QListWidget, QPushButton, QTabWidget, QVBoxLayout

        super().__init__(parent)
        self.setWindowTitle("Gamepad Controls")
        self.pm = pm
        self.pads = pads if pads is not None else instance()
        self.settings = load_settings(pm.meta)
        self.lists: dict[str, QListWidget] = {}
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        for context in (REVIEW, OTHER):
            lst = QListWidget()
            lst.setWordWrap(True)
            lst.itemClicked.connect(lambda item, c=context: self.edit(c, item.data(Qt.ItemDataRole.UserRole)))
            self.lists[context] = lst
            self.tabs.addTab(lst, CONTEXT_TITLES[context])
        layout.addWidget(self.tabs)
        custom = QPushButton("Add Keyboard Shortcut…")
        custom.clicked.connect(self._add_custom)
        layout.addWidget(custom)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.RestoreDefaults | QDialogButtonBox.StandardButton.Close
        )
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self._defaults)
        layout.addWidget(buttons)
        self.refresh()

    def context(self) -> str:
        return (REVIEW, OTHER)[self.tabs.currentIndex()]

    def actions_in(self, context: str) -> list[str]:
        ids = [a.id for a in ACTIONS if context in a.contexts]
        return ids + sorted(a for a in self.settings.bindings.get(context, {}) if a.startswith(KEY_PREFIX))

    def summary(self, context: str, action_id: str) -> str:
        items = self.settings.bindings.get(context, {}).get(action_id, [])
        return ", ".join(binding_label(b, context) for b in items) or "—"

    def refresh(self) -> None:
        from aqt.qt import QListWidgetItem

        for context, lst in self.lists.items():
            row = lst.currentRow()
            lst.clear()
            for action_id in self.actions_in(context):
                item = QListWidgetItem(f"{action_label(action_id)}\n    {self.summary(context, action_id)}")
                item.setData(Qt.ItemDataRole.UserRole, action_id)
                lst.addItem(item)
            lst.setCurrentRow(max(0, row))

    def edit(self, context: str, action_id: str) -> None:
        BindingsDialog(self, context, action_id).exec()
        self.refresh()

    def save(self) -> None:
        current = load_settings(self.pm.meta)
        current.bindings = self.settings.bindings
        save_settings(self.pm, current)
        settings_changed()

    def _add_custom(self) -> None:
        from aqt.utils import getText

        text, ok = getText(
            "Keyboard shortcut to run, as Anki's menus show it (such as Ctrl+Shift+D or *). "
            "Add-ons' shortcuts work too.",
            parent=self,
        )
        seq = QKeySequence(text.strip()) if ok else QKeySequence()
        if seq.isEmpty():
            return
        context = self.context()
        action_id = KEY_PREFIX + seq.toString()
        self.settings.bindings.setdefault(context, {}).setdefault(action_id, [])
        self.save()
        self.refresh()
        self.edit(context, action_id)

    def _defaults(self) -> None:
        enabled = self.settings.enabled
        self.settings = Settings.from_dict({"version": VERSION, "enabled": enabled})
        self.save()
        self.refresh()


class BindingsDialog(QDialog):
    """One action's buttons: add one by pressing it, remove one by tapping
    it (AnkiDroid's control dialog)."""

    def __init__(self, controls: ControlsDialog, context: str, action_id: str) -> None:
        from aqt.qt import QDialogButtonBox, QLabel, QListWidget, QPushButton, QVBoxLayout

        super().__init__(controls)
        self.controls = controls
        self.context = context
        self.action_id = action_id
        self.setWindowTitle(action_label(action_id))
        layout = QVBoxLayout(self)
        add = QPushButton("Add Button…")
        add.clicked.connect(self._add)
        layout.addWidget(add)
        hint = QLabel("Tap a button below to remove it.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.list = QListWidget()
        self.list.itemClicked.connect(self._remove)
        layout.addWidget(self.list)
        if action_id.startswith(KEY_PREFIX):
            delete = QPushButton("Delete This Shortcut")
            delete.clicked.connect(self._delete)
            layout.addWidget(delete)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.refresh()

    def items(self) -> list[str]:
        return self.controls.settings.bindings.get(self.context, {}).get(self.action_id, [])

    def refresh(self) -> None:
        from aqt.qt import QListWidgetItem

        self.list.clear()
        for item in self.items():
            row = QListWidgetItem(f"Remove {binding_label(item, self.context)}")
            row.setData(Qt.ItemDataRole.UserRole, item)
            self.list.addItem(row)

    def _remove(self, row: Any) -> None:
        self.controls.settings.remove(self.context, self.action_id, row.data(Qt.ItemDataRole.UserRole))
        self.controls.save()
        self.refresh()

    def _delete(self) -> None:
        self.controls.settings.bindings.get(self.context, {}).pop(self.action_id, None)
        self.controls.save()
        self.accept()

    def _add(self) -> None:
        picker = ButtonPicker(self, self.controls, self.context, self.action_id)
        if picker.exec() and picker.chosen:
            self.controls.settings.add(self.context, self.action_id, picker.chosen)
            self.controls.save()
            self.refresh()


class ButtonPicker(QDialog):
    """Press a button on the controller (AnkiDroid's key picker); while
    studying, choose the card side too. Says which action has it now: OK
    moves it here."""

    def __init__(self, parent: QWidget, controls: ControlsDialog, context: str, action_id: str) -> None:
        from aqt.qt import QButtonGroup, QDialogButtonBox, QHBoxLayout, QLabel, QRadioButton, QVBoxLayout

        super().__init__(parent)
        self.controls = controls
        self.context = context
        self.action_id = action_id
        self.button_name: str | None = None
        self.chosen: str | None = None
        self.setWindowTitle(action_label(action_id))
        layout = QVBoxLayout(self)
        pads = controls.pads
        connected = bool(pads and pads.controllers)
        prompt = QLabel(
            "Press a button on the controller."
            if connected
            else "Press a button on the controller. (None is connected now: pair one "
            "in the system's Bluetooth settings, or plug one in.)"
        )
        prompt.setWordWrap(True)
        layout.addWidget(prompt)
        self.pressed = QLabel("…")
        font = self.pressed.font()
        # Android's fonts have a pixel size, not a point size
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * 1.6)
        else:
            font.setPixelSize(round(font.pixelSize() * 1.6))
        font.setBold(True)
        self.pressed.setFont(font)
        self.pressed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.pressed)
        self.where = QLabel("")
        self.where.setWordWrap(True)
        self.where.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.where)
        self.sides: dict[str, QRadioButton] = {}
        if context == REVIEW:
            row = QHBoxLayout()
            group = QButtonGroup(self)
            default = ANSWER if action_id in ANSWER_EASE else QUESTION if action_id == "show-answer" else BOTH
            for side, text in ((QUESTION, "Question"), (ANSWER, "Answer"), (BOTH, "Both")):
                radio = QRadioButton(text)
                radio.setChecked(side == default)
                radio.toggled.connect(self._update)
                group.addButton(radio)
                row.addWidget(radio)
                self.sides[side] = radio
            layout.addLayout(row)
        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)
        self.box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.box.accepted.connect(self._ok)
        self.box.rejected.connect(self.reject)
        layout.addWidget(self.box)
        self._update()
        if pads is not None:
            pads.capture = self.on_press
        self.finished.connect(self._stop)

    def side(self) -> str:
        for side, radio in self.sides.items():
            if radio.isChecked():
                return side
        return BOTH

    def on_press(self, name: str) -> None:
        self.button_name = name
        self._update()

    def candidate(self) -> str | None:
        return binding(self.button_name, self.side()) if self.button_name else None

    def _update(self) -> None:
        ok = self.box.button(self.box.StandardButton.Ok)
        item = self.candidate()
        ok.setEnabled(item is not None)
        if self.button_name is None:
            return
        self.pressed.setText(BUTTON_LABELS[self.button_name])
        self.where.setText(BUTTON_HELP[self.button_name])
        owner = self.controls.settings.owner(self.context, item) if item else None
        if owner and owner != self.action_id:
            self.warning.setText(f"Now used for “{action_label(owner)}”. OK moves it here.")
        else:
            self.warning.setText("")

    def _ok(self) -> None:
        self.chosen = self.candidate()
        self.accept()

    def _stop(self) -> None:
        pads = self.controls.pads
        if pads is not None and pads.capture == self.on_press:
            pads.capture = None
