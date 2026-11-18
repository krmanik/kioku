"""What kioku.gamepad relies on in Anki, checked against the Anki release
Kioku is built with: the keyboard shortcuts its actions run, the card side,
and the deck list markup the d-pad highlight reads. A failure after an Anki
update means kioku/gamepad.py needs a look (see docs/testing.md)."""

from __future__ import annotations

import os
from functools import partial
from html.parser import HTMLParser
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import anki.lang

anki.lang.set_lang("en")  # aqt.deckbrowser translates at import

import aqt
import aqt.deckbrowser
import aqt.main
import aqt.reviewer
from aqt.qt import QApplication, QKeySequence, Qt

from kioku import gamepad as g

app = QApplication.instance() or QApplication([])


class Named:
    """Stands in for Anki objects: every attribute is a function that
    knows its name."""

    def __init__(self, **attrs) -> None:  # type: ignore[no-untyped-def]
        self.__dict__.update(attrs)

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        if name.startswith("__"):
            raise AttributeError(name)

        def fn(*args):  # type: ignore[no-untyped-def]
            return name if not args else (name, *args)

        fn.__name__ = name
        return fn


def _name(fn) -> object:  # type: ignore[no-untyped-def]
    if isinstance(fn, partial):
        return (fn.func.__name__, *fn.args)
    return fn.__name__


def _keys(pairs) -> dict[str, object]:  # type: ignore[no-untyped-def]
    out = {}
    for key, fn in pairs:
        if isinstance(key, Qt.Key):
            key = QKeySequence(key).toString()
        out[QKeySequence(key).toString()] = fn
    return out


def test_review_shortcuts(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pm = SimpleNamespace(
        default_answer_keys={1: "1", 2: "2", 3: "3", 4: "4"},
        get_answer_key=lambda ease: {1: "j", 2: "k", 3: "l", 4: ";"}[ease],
    )
    mw = Named(flags=SimpleNamespace(all=lambda: [SimpleNamespace(index=i) for i in range(1, 8)]), pm=pm)
    monkeypatch.setattr(aqt, "mw", mw, raising=False)
    reviewer = Named(
        mw=mw, set_flag_func=lambda i: partial(Named().set_flag, i), korean_shortcuts=lambda: []
    )
    keys = _keys(aqt.reviewer.Reviewer._shortcutKeys(reviewer))

    expected = {
        "show-answer": "onEnterKey",
        "replay": "replayAudio",
        "pause-audio": "on_pause_audio",
        "more": "showContextMenu",
        "edit": "onEditCurrent",
        "mark": "toggle_mark_on_current_note",
        "bury-card": "bury_current_card",
        "bury-note": "bury_current_note",
        "suspend-card": "suspend_current_card",
        "suspend-note": "suspend_current_note",
        "card-info": "on_card_info",
        "deck-options": "onOptions",
        "replay-voice": "onReplayRecorded",
        "record-voice": "onRecordVoice",
    }
    for action_id, method in expected.items():
        shortcut = QKeySequence(g.ACTION_BY_ID[action_id].shortcut).toString()
        assert shortcut in keys, f"{action_id}: Anki has no {shortcut!r} shortcut in review"
        assert _name(keys[shortcut]) == method, f"{action_id}: {shortcut!r} runs {_name(keys[shortcut])}"
    for i in range(1, 5):
        assert _name(keys[f"Ctrl+{i}"]) == ("set_flag", i)
    # the answer keys come from Anki's preferences (pm.get_answer_key)
    for action_id, ease in g.ANSWER_EASE.items():
        key = QKeySequence(pm.get_answer_key(ease)).toString()
        assert _name(keys[key]) == ("_answerCard", ease), action_id


def test_main_window_shortcuts_and_study_key() -> None:
    applied: list = []
    moved: list = []
    aqt.main.AnkiQt.setupKeys(Named(applyShortcuts=applied.extend, moveToState=moved.append))
    keys = _keys(applied)
    assert _name(keys["S"]) == "onStudyKey"
    assert _name(keys["A"]) == "onAddCard"
    assert _name(keys["B"]) == "onBrowse"
    assert _name(keys["Y"]) == "on_sync_button_clicked"
    keys["D"]()
    assert moved == ["deckBrowser"]
    for action_id in ("decks", "study", "add", "browse", "sync"):
        assert QKeySequence(g.ACTION_BY_ID[action_id].shortcut).toString() in keys

    # S on a deck's overview starts studying
    calls: list = []
    overview = Named(state="overview", col=Named(startTimebox=lambda: calls.append("timebox")),
                     moveToState=calls.append)
    aqt.main.AnkiQt.onStudyKey(overview)
    assert calls == ["timebox", "review"]


def test_card_side_names() -> None:
    import inspect

    source = inspect.getsource(aqt.reviewer.Reviewer)
    assert 'self.state = "question"' in source and 'self.state = "answer"' in source


class Rows(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict] = []
        self.link: str | None = None

    def handle_starttag(self, tag, attrs) -> None:  # type: ignore[no-untyped-def]
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "tr" and "deck" in classes:
            self.rows.append({"id": a.get("id"), "classes": classes, "collapse": None, "deck": False})
        elif tag == "a" and self.rows and "collapse" in classes:
            self.link = "collapse"
        elif tag == "a" and self.rows and "deck" in classes:
            self.rows[-1]["deck"] = True

    def handle_data(self, data) -> None:  # type: ignore[no-untyped-def]
        if self.link == "collapse":
            self.rows[-1]["collapse"] = data.strip()
            self.link = None


def test_deck_list_markup() -> None:
    from anki.decks import DeckTreeNode

    child = DeckTreeNode(deck_id=2, name="Child", level=2)
    parent = DeckTreeNode(deck_id=1, name="Parent", level=1, children=[child])
    folded = DeckTreeNode(deck_id=3, name="Folded", level=1, collapsed=True, children=[child])
    browser = Named()
    browser._render_deck_node = lambda n, c: aqt.deckbrowser.DeckBrowser._render_deck_node(browser, n, c)
    ctx = aqt.deckbrowser.RenderDeckNodeContext(current_deck_id=1)
    html = "".join(aqt.deckbrowser.DeckBrowser._render_deck_node(browser, n, ctx) for n in (parent, folded))
    rows = Rows()
    rows.feed(html)
    by_id = {r["id"]: r for r in rows.rows}
    # DECK_SCRIPT: tr.deck rows with the deck id, .current, a.collapse
    # showing "+" when collapsed, a.deck to open
    assert set(by_id) == {"1", "2", "3"}
    assert "current" in by_id["1"]["classes"]
    assert by_id["1"]["collapse"] != "+" and by_id["3"]["collapse"] == "+"
    assert all(r["deck"] for r in rows.rows)
