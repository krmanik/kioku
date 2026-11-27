"""kioku.hidebars: with Preferences › Hide top/bottom bar during review,
Anki shows the bars only when the mouse pointer leaves the card, so on a
touch screen the answer buttons never came back. A plain tap on the card
shows the hidden bars, the next one hides them, answering hides them."""

from __future__ import annotations

import types

from aqt.reviewer import Reviewer

from kioku import hidebars


class Bar:
    def __init__(self, hides: bool) -> None:
        self.hidden = False
        self.hides = hides
        self.hide_timer = types.SimpleNamespace(stop=lambda: None)

    def show(self) -> None:
        self.hidden = False

    def hide_if_allowed(self) -> None:
        if self.hides:
            self.hidden = True


def _mw(monkeypatch, top: bool, bottom: bool, state: str = "review"):  # type: ignore[no-untyped-def]
    pm = types.SimpleNamespace(hide_top_bar=lambda: top, hide_bottom_bar=lambda: bottom)
    mw = types.SimpleNamespace(state=state, pm=pm, toolbarWeb=Bar(top), bottomWeb=Bar(bottom))
    monkeypatch.setattr(hidebars.aqt, "mw", mw, raising=False)
    return mw


def tap() -> tuple[bool, object]:
    return hidebars._on_message((False, None), hidebars.COMMAND, None)


def test_tap_toggles_hidden_bars(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    mw = _mw(monkeypatch, top=False, bottom=True)
    mw.bottomWeb.hidden = True
    assert tap() == (True, None)
    assert not mw.bottomWeb.hidden
    tap()
    assert mw.bottomWeb.hidden and not mw.toolbarWeb.hidden  # only what the prefs hide


def test_answering_hides_them_again(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    mw = _mw(monkeypatch, top=True, bottom=True)
    hidebars._hide()
    assert mw.toolbarWeb.hidden and mw.bottomWeb.hidden


def test_nothing_without_the_preferences_or_outside_review(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    mw = _mw(monkeypatch, top=False, bottom=False)
    tap()
    assert not mw.bottomWeb.hidden
    mw = _mw(monkeypatch, top=True, bottom=True, state="overview")
    hidebars._hide()
    assert not mw.bottomWeb.hidden


def test_other_messages_pass_through() -> None:
    assert hidebars._on_message((False, None), "ans", None) == (False, None)


def test_script_only_on_the_reviewer() -> None:
    content = types.SimpleNamespace(head="")
    hidebars._add_tap(content, object())
    assert content.head == ""
    hidebars._add_tap(content, Reviewer.__new__(Reviewer))
    assert hidebars.COMMAND in content.head and "closest(ACTIVE)" in content.head
