"""kioku:// links (kioku/urlscheme.py): parsing and building notes on a real
collection; the Qt hand-off is tested on the devices."""

from __future__ import annotations

import pytest
from anki.collection import Collection

from kioku import urlscheme
from kioku.urlscheme import LinkError, build_note, fill_media, parse


@pytest.fixture
def col(tmp_path):
    col = Collection(str(tmp_path / "collection.anki2"))
    col.decks.id("Lang::Words")
    yield col
    col.close()


def test_parse_ankimobile_form() -> None:
    link = parse(
        "kioku://x-callback-url/addnote?profile=User%201&type=Basic&deck=Default"
        "&fldFront=C++%20%26%20more&fldBack=a%3Cbr%3Eb&tags=x%20y&dupes=1"
    )
    assert link.action == "addnote"
    assert link.params == {
        "profile": "User 1",
        "type": "Basic",
        "deck": "Default",
        "fldFront": "C++ & more",  # "+" stays "+"
        "fldBack": "a<br>b",
        "tags": "x y",
        "dupes": "1",
    }


@pytest.mark.parametrize(
    "url,action",
    [
        ("kioku://x-callback-url/sync", "sync"),
        ("kioku://sync", "sync"),
        ("KIOKU://X-Callback-URL/Search?query=deck:current", "search"),
        ("kioku://", ""),
    ],
)
def test_parse_actions(url: str, action: str) -> None:
    assert parse(url).action == action


def test_parse_other_scheme() -> None:
    with pytest.raises(LinkError):
        parse("anki://x-callback-url/sync")


def test_build_and_add(col: Collection) -> None:
    link = parse(
        "kioku://x-callback-url/addnote?type=Basic&deck=Lang%3A%3AWords"
        "&fldFront=hund&fldBack=dog&tags=de%20noun&x-success=shortcuts%3A%2F%2F"
    )
    new = build_note(col, link.params, "User 1")
    assert new.deck_id == col.decks.id_for_name("Lang::Words")
    assert new.x_success == "shortcuts://"
    col.add_note(new.note, new.deck_id)
    note = col.get_note(col.find_notes("hund")[0])
    assert note["Back"] == "dog"
    assert note.tags == ["de", "noun"]
    assert col.decks.name(note.cards()[0].did) == "Lang::Words"


def test_defaults_for_type_and_deck(col: Collection) -> None:
    new = build_note(col, {"fldFront": "x"})
    assert new.note.note_type()["name"] == "Basic"
    assert new.deck_id == 1


def test_duplicates(col: Collection) -> None:
    params = {"type": "Basic", "fldFront": "same"}
    first = build_note(col, params)
    col.add_note(first.note, first.deck_id)
    with pytest.raises(LinkError, match="already exists"):
        build_note(col, params)
    build_note(col, {**params, "dupes": "1"})


@pytest.mark.parametrize(
    "params,message",
    [
        ({"type": "Nope", "fldFront": "x"}, 'no note type "Nope"'),
        ({"deck": "Nope", "fldFront": "x"}, 'no deck "Nope"'),
        ({"fldWrong": "x"}, 'no field "Wrong"'),
        ({"fldBack": "x"}, "first field"),
        ({"fldFront": "x", "profile": "Other"}, 'profile "Other"'),
        ({"fldFront": "x", "x-success": "kioku://sync"}, "x-success"),
        ({"fldFront": "x", "x-success": "file:///etc/passwd"}, "x-success"),
    ],
)
def test_refused(col: Collection, params: dict, message: str) -> None:
    with pytest.raises(LinkError, match=message):
        build_note(col, params, "User 1")


def test_media_links(col: Collection) -> None:
    params = {
        "fldFront": "http://example.com/img/cat.JPG",
        "fldBack": "https://example.com/getAudio?id=12&fakePath=meow.mp3",
    }
    new = build_note(col, params)
    assert new.downloads == {
        "Front": ("http://example.com/img/cat.JPG", "jpg"),
        "Back": ("https://example.com/getAudio?id=12&fakePath=meow.mp3", "mp3"),
    }
    fill_media(col, new, {"Front": b"jpeg", "Back": b"mp3"})
    assert new.note["Front"] == '<img src="cat.jpg">'  # Anki lowercases the extension
    assert new.note["Back"] == "[sound:meow.mp3]"
    assert col.media.have("cat.jpg") and col.media.have("meow.mp3")


def test_not_media() -> None:
    assert urlscheme.media_link("see http://example.com/a.jpg") is None
    assert urlscheme.media_link("http://example.com/page.html") is None
    assert urlscheme.media_name("http://e.com/a/..%2F..%2Fx.png") == "_.._x.png"
