"""kioku.gamepad: bindings, settings, and buttons to Anki's shortcuts."""

from __future__ import annotations

import os
import pickle
import sqlite3
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import aqt
import pytest
from aqt.qt import (
    QApplication,
    QDialog,
    QKeySequence,
    QPushButton,
    QShortcut,
    QVBoxLayout,
    QWidget,
)

from kioku import gamepad as g

app = QApplication.instance() or QApplication([])


class Web:
    def __init__(self) -> None:
        self.evals: list[str] = []

    def eval(self, js: str) -> None:
        self.evals.append(js)

    def evalWithCallback(self, js: str, cb) -> None:  # type: ignore[no-untyped-def]
        self.evals.append(js)
        cb("42")


class Reviewer:
    state = "question"


class DeckBrowser:
    def __init__(self) -> None:
        self.web = Web()


class DB:
    def __init__(self) -> None:
        self.con = sqlite3.connect(":memory:")
        self.con.execute("create table profiles (name text, data blob)")
        self.con.execute("insert into profiles values ('_global', null)")

    def execute(self, sql: str, *args) -> None:  # type: ignore[no-untyped-def]
        self.con.execute(sql, args)

    def commit(self) -> None:
        self.con.commit()


class PM:
    def __init__(self) -> None:
        self.meta: dict = {}
        self.db = DB()
        self.answer_keys = {1: "1", 2: "2", 3: "3", 4: "4"}

    def _pickle(self, obj) -> bytes:  # type: ignore[no-untyped-def]
        return pickle.dumps(obj)

    def get_answer_key(self, ease: int) -> str | None:
        return self.answer_keys.get(ease)


# Anki's main window and reviewer shortcuts that kioku.gamepad uses
SHORTCUTS = [" ", "1", "2", "3", "4", "j", "r", "m", "e", "d", "s", "a", "b", "y", "Ctrl+Shift+D"]


class MainWindow(QWidget):
    def __init__(self, state: str) -> None:
        super().__init__()
        self.state = state
        self.log: list = []
        self.reviewer = Reviewer()
        self.deckBrowser = DeckBrowser()
        self.web = Web()
        self.pm = PM()
        for key in SHORTCUTS:
            QShortcut(QKeySequence(key), self).activated.connect(lambda k=key: self.log.append(k))

    def moveToState(self, state: str) -> None:
        self.log.append(("state", state))

    def undo(self) -> None:
        self.log.append("undo")


@pytest.fixture
def make(monkeypatch):  # type: ignore[no-untyped-def]
    shown: list[QWidget] = []

    def make(state: str) -> tuple[MainWindow, g.Gamepads]:
        mw = MainWindow(state)
        monkeypatch.setattr(aqt, "mw", mw, raising=False)
        mw.show()  # Anki's shortcuts count only in a shown window
        shown.append(mw)
        return mw, g.Gamepads()

    yield make
    for w in shown:
        w.hide()


def tap(pads: g.Gamepads, name: str) -> None:
    pads.button(name, True)
    pads.button(name, False)


# --- bindings and settings


def test_bindings() -> None:
    assert g.parse_binding("A@answer") == ("A", g.ANSWER)
    assert g.parse_binding("A") == ("A", g.BOTH)
    assert g.parse_binding("Q") is None and g.parse_binding("A@x") is None
    assert g.overlaps("A", "A@answer") and not g.overlaps("A@question", "A@answer")
    assert not g.overlaps("A", "B")
    assert g.binding_label("A@answer") == "A (answer)"
    assert g.binding_label("Up", g.OTHER) == "D-pad ↑"


def test_settings_defaults_round_trip_and_side() -> None:
    s = g.load_settings({})
    assert s.enabled
    assert s.action_for(g.REVIEW, "A", g.QUESTION) == "show-answer"
    assert s.action_for(g.REVIEW, "A", g.ANSWER) == "good"
    assert s.action_for(g.REVIEW, "B", g.QUESTION) == ""
    s.add(g.REVIEW, "replay", "B")  # both sides: takes B@answer from Again
    assert s.bindings[g.REVIEW]["again"] == []
    assert s.action_for(g.REVIEW, "B", g.QUESTION) == "replay"
    s.add(g.REVIEW, "again", "B@answer")  # a side binding wins over "both"
    assert s.bindings[g.REVIEW]["replay"] == ["R1"]
    pm = PM()
    g.save_settings(pm, s)
    stored = pickle.loads(pm.db.con.execute("select data from profiles").fetchone()[0])
    assert stored[g.META_KEY]["version"] == g.VERSION
    again = g.load_settings(pm.meta)
    assert again.bindings == s.bindings


def test_settings_tolerate_old_and_new_kioku() -> None:
    # not version 2 (or garbage): defaults
    assert g.load_settings({g.META_KEY: {"review": {"A": "again"}}}).bindings == g.load_settings({}).bindings
    assert g.load_settings({g.META_KEY: "junk"}).enabled
    # unknown actions and bindings dropped; an action missing from the saved
    # settings (added by a newer Kioku) gets its defaults unless they clash
    saved = {
        "version": g.VERSION,
        "review": {"gone-action": ["A"], "again": ["A@answer", "Nope"], "key:Ctrl+Shift+D": ["L3"]},
    }
    s = g.load_settings({g.META_KEY: saved})
    assert "gone-action" not in s.bindings[g.REVIEW]
    assert s.bindings[g.REVIEW]["again"] == ["A@answer"]
    assert s.bindings[g.REVIEW]["key:Ctrl+Shift+D"] == ["L3"]
    assert s.bindings[g.REVIEW]["good"] == []  # A@answer is taken
    assert s.bindings[g.REVIEW]["show-answer"] == ["A@question"]
    assert s.bindings[g.OTHER] == g.DEFAULTS[g.OTHER]


# --- buttons to Anki's shortcuts


def test_review_question_and_answer(make) -> None:  # type: ignore[no-untyped-def]
    mw, pads = make("review")
    for name in ("B", "X", "Y"):  # answers do nothing on the question
        tap(pads, name)
    assert mw.log == []
    tap(pads, "A")
    assert mw.log == [" "]
    mw.reviewer.state = "answer"
    for name in ("A", "B", "X", "Y"):
        tap(pads, name)
    assert mw.log[1:] == ["3", "1", "2", "4"]
    # A on the answer never runs Space (Anki's Space answers Good there)
    mw.log.clear()
    pads.settings.bindings[g.REVIEW]["show-answer"] = ["A"]
    pads.settings.bindings[g.REVIEW]["good"] = []
    tap(pads, "A")
    assert mw.log == []


def test_answer_keys_from_anki_preferences(make) -> None:  # type: ignore[no-untyped-def]
    mw, pads = make("review")
    mw.reviewer.state = "answer"
    mw.pm.answer_keys[1] = "j"
    tap(pads, "B")
    assert mw.log == ["j"]


def test_review_other_buttons(make) -> None:  # type: ignore[no-untyped-def]
    mw, pads = make("review")
    for name in ("L1", "R1", "Menu", "View"):
        tap(pads, name)
    assert mw.log == ["undo", "r", "m", ("state", "overview")]
    tap(pads, "Down")
    assert "scrollBy" in mw.web.evals[-1]


def test_deck_list_and_overview(make) -> None:  # type: ignore[no-untyped-def]
    mw, pads = make("deckBrowser")
    tap(pads, "Down")
    assert pads.actions.deck_id == "42"
    assert '"down"' in mw.deckBrowser.web.evals[-1]
    tap(pads, "A")
    assert '"42", "select"' in mw.deckBrowser.web.evals[-1]
    tap(pads, "Y")
    tap(pads, "B")  # back on the deck list: nothing
    assert mw.log == ["y"]
    mw.state = "overview"
    tap(pads, "A")
    tap(pads, "B")
    assert mw.log[1:] == ["s", ("state", "deckBrowser")]


def test_custom_shortcut(make) -> None:  # type: ignore[no-untyped-def]
    mw, pads = make("review")
    pads.settings.add(g.REVIEW, "key:Ctrl+Shift+D", "L3")
    tap(pads, "L3")
    assert mw.log == ["Ctrl+Shift+D"]


def test_sources_and_axes(make) -> None:  # type: ignore[no-untyped-def]
    mw, pads = make("review")
    pads.button("A", True, "key")
    pads.button("A", True, "pad")
    pads.button("A", False, "key")
    pads.button("A", False, "pad")
    assert mw.log == [" "]
    pads.settings.add(g.REVIEW, "replay", "L2")
    pads.axes("triggers", 0.9, 0.0)
    pads.axes("triggers", 0.0, 0.0)
    assert mw.log[-1] == "r"
    before = len(mw.web.evals)
    pads.axes("left", 0.0, 0.8)
    pads.axes("left", 0.0, 0.9)
    assert len(mw.web.evals) == before + 1
    pads.axes("left", 0.0, 0.0)
    assert pads._repeat_button is None
    pads.axes("right", 0.0, 1.0)
    assert pads._scroller.isActive()
    pads._on_scroll()
    assert f"top: {g.SCROLL_SPEED}" in mw.web.evals[-1]
    pads.axes("right", 0.0, 0.1)
    assert not pads._scroller.isActive()


def test_repeat_only_for_moves(make) -> None:  # type: ignore[no-untyped-def]
    mw, pads = make("review")
    pads.button("Down", True)
    assert pads._repeat.isActive()
    pads._on_repeat()
    assert sum("scrollBy" in js for js in mw.web.evals) == 2
    pads.button("Down", False)
    assert not pads._repeat.isActive()
    mw.reviewer.state = "answer"
    pads.button("B", True)
    assert not pads._repeat.isActive()


def test_disabled_and_capture(make) -> None:  # type: ignore[no-untyped-def]
    mw, pads = make("review")
    pads.settings.enabled = False
    tap(pads, "A")
    assert mw.log == []
    pressed: list[str] = []
    pads.capture = pressed.append
    tap(pads, "A")
    pads.axes("triggers", 1.0, 0.0)
    assert pressed == ["A", "L2"] and mw.log == []


def test_dialog_navigation(make) -> None:  # type: ignore[no-untyped-def]
    mw, pads = make("deckBrowser")
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    clicked: list[str] = []
    first, second = QPushButton("one"), QPushButton("two")
    first.clicked.connect(lambda: clicked.append("one"))
    second.clicked.connect(lambda: clicked.append("two"))
    layout.addWidget(first)
    layout.addWidget(second)
    dialog.show()
    dialog.activateWindow()
    assert g._target_window() is dialog
    first.setFocus()
    tap(pads, "R1")
    assert dialog.focusWidget() is second
    tap(pads, "A")
    deadline = time.time() + 2
    while not clicked and time.time() < deadline:
        QApplication.processEvents()
    assert clicked == ["two"]
    tap(pads, "B")
    assert not dialog.isVisible()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert mw.log == []


# --- Controls dialog


def test_controls_dialog(make) -> None:  # type: ignore[no-untyped-def]
    mw, pads = make("deckBrowser")
    pads.controllers["1"] = "Pad"
    pm = PM()
    controls = g.ControlsDialog(mw, pm, pads)
    rows = controls.lists[g.REVIEW]
    texts = [rows.item(i).text() for i in range(rows.count())]
    assert "Again\n    B (answer)" in texts

    # press to bind: B on the answer side for Good, taken from Again
    bindings = g.BindingsDialog(controls, g.REVIEW, "good")
    picker = g.ButtonPicker(bindings, controls, g.REVIEW, "good")
    assert pads.capture == picker.on_press
    assert picker.side() == g.ANSWER
    tap(pads, "B")
    assert picker.pressed.text() == "B"
    assert "Again" in picker.warning.text()
    picker._ok()
    assert picker.chosen == "B@answer" and pads.capture is None
    controls.settings.add(g.REVIEW, "good", picker.chosen)
    controls.save()
    saved = pm.meta[g.META_KEY]["review"]
    assert saved["good"] == ["A@answer", "B@answer"] and saved["again"] == []

    # remove by tapping its row
    bindings.refresh()
    bindings._remove(bindings.list.item(0))
    assert pm.meta[g.META_KEY]["review"]["good"] == ["B@answer"]

    # a custom shortcut action, then deleted
    controls.settings.bindings[g.REVIEW]["key:Ctrl+Shift+D"] = ["L3"]
    controls.save()
    controls.refresh()
    assert any("Shortcut Ctrl+Shift+D" in rows.item(i).text() for i in range(rows.count()))
    g.BindingsDialog(controls, g.REVIEW, "key:Ctrl+Shift+D")._delete()
    assert "key:Ctrl+Shift+D" not in pm.meta[g.META_KEY]["review"]

    controls._defaults()
    assert pm.meta[g.META_KEY]["review"] == g.DEFAULTS[g.REVIEW]
