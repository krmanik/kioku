# Kioku's in-app test suite: real user flows in the running app (iOS, Android,
# the iOS Simulator), sent through the development command channel
# (shared/python/kioku/devtools.py) by shared/tools/apptest.py, which prepends
#
#   EXPECTED_VERSION = "26.09.4"   # Anki version the build must report
#   ONLY = []                      # test names to run (empty: all)
#   NETWORK = True                 # run the tests that need the internet
#
# Every test is a generator: `yield seconds` waits, `yield Until(cond)` waits
# for a condition, `yield Js(web, code)` evaluates JavaScript in a web view and
# returns its result. Each result is one JSON line in
# Documents/.kioku-test/results.jsonl, the last one
# {"done": true}. Everything the tests create lives in the deck "Kioku Test"
# and is removed again at the end; the profile's other data is never changed.

import json
import os
import sys
import threading
import time
import traceback
import urllib.request

import aqt
from aqt.qt import QApplication, QTimer, QWidget
from aqt.webview import AnkiWebView

try:
    EXPECTED_VERSION  # noqa: B018
except NameError:
    EXPECTED_VERSION = ""
    ONLY = []
    NETWORK = True

import kioku_platform

mw = aqt.mw
WORK = os.path.join(kioku_platform.documents_dir(), ".kioku-test")
RESULTS = os.path.join(WORK, "results.jsonl")
DECK = "Kioku Test"
TAG = "kiokutest"
STEP_TIMEOUT = 45.0
MEDIA = "kiokutest-dot.png"
# a 2x2 red PNG
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000002000000020802000000fdd49a73"
    "0000001649444154789c63f8cfc0f01f0418182018fe03000035fe05fb6a4d8ab7"
    "0000000049454e44ae426082"
)


class Until:
    def __init__(self, cond, timeout: float = 20.0, what: str = "") -> None:
        self.cond, self.timeout, self.what = cond, timeout, what


class Js:
    def __init__(self, web: AnkiWebView, code: str, timeout: float = 15.0) -> None:
        self.web, self.code, self.timeout = web, code, timeout


class Skip(Exception):
    pass


def check(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


# --- helpers -----------------------------------------------------------------


def col():
    return mw.col


def deck_id() -> int:
    return col().decks.id(DECK)


def test_note_ids() -> list[int]:
    return list(col().find_notes(f'"deck:{DECK}" tag:{TAG}'))


def add_basic(front: str, back: str):
    note = col().new_note(col().models.by_name("Basic"))
    note["Front"], note["Back"] = front, back
    note.tags = [TAG]
    col().add_note(note, deck_id())
    return note


def windows_of(type_name: str) -> list[QWidget]:
    return [
        w
        for w in QApplication.topLevelWidgets()
        if w.isVisible() and type(w).__name__ == type_name
    ]


def web_in(widget: QWidget) -> AnkiWebView:
    webs = [w for w in widget.findChildren(AnkiWebView)]
    check(bool(webs), f"no web view in {type(widget).__name__}")
    return webs[0]


def close_window(w: QWidget) -> None:
    from kioku import windows

    windows._back(w)


def close_extra_windows() -> None:
    """Close what a test left open (message boxes too), like Back."""
    from aqt.qt import QMessageBox

    for w in QApplication.topLevelWidgets():
        if w is mw or not w.isVisible() or not w.isWindow():
            continue
        if isinstance(w, QMessageBox):
            w.done(0)
        elif type(w).__name__ != "ProfileManager":
            try:
                close_window(w)
            except Exception:
                pass


def body_text(web: AnkiWebView) -> Js:
    return Js(web, "document.body ? document.body.innerText : ''")


# JavaScript run with deep(selector), which also searches open shadow roots
# (the Svelte pages: editor, import). Wrapped in a function: a page keeps
# top-level declarations between evaluations, so a second `const` would fail.
def deep_js(body: str) -> str:
    return """(() => {
const deep = (sel, root = document) => {
  const out = [...root.querySelectorAll(sel)];
  for (const el of root.querySelectorAll('*')) {
    if (el.shadowRoot) out.push(...deep(sel, el.shadowRoot));
  }
  return out;
};
%s
})()""" % body


def qa_text(web: AnkiWebView) -> Js:
    """The card's text in the reviewer."""
    return Js(web, "(() => { const qa = document.getElementById('qa'); return qa ? qa.innerText : null; })()")


def picture_width(web: AnkiWebView) -> Js:
    return Js(web, "(() => { const i = [...document.images].find(i => i.src.includes('%s'));"
                   " return i ? (i.complete ? i.naturalWidth : 0) : -1; })()" % MEDIA)


def revlog_count(cid: int) -> int:
    return col().db.scalar("select count() from revlog where cid = ?", cid)


def in_thread(fn):
    """Run fn off the main thread; returns a holder that gets 'value'/'error'."""
    box: dict = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except BaseException as err:  # noqa: BLE001
            box["error"] = err

    threading.Thread(target=run, daemon=True).start()
    return box


# --- tests -------------------------------------------------------------------


def t_version():
    import platform as pyplatform

    from aqt.qt import QT_VERSION_STR, PYQT_VERSION_STR

    info = (
        f"Anki {aqt.appVersion}, Qt {QT_VERSION_STR}, PyQt {PYQT_VERSION_STR}, "
        f"Python {pyplatform.python_version()}, {sys.platform}"
    )
    if EXPECTED_VERSION:
        check(aqt.appVersion == EXPECTED_VERSION, f"{info}; expected Anki {EXPECTED_VERSION}")
    yield 0
    return info


def t_profile():
    check(mw.pm.name is not None, "no profile loaded")
    check(col() is not None, "no collection open")
    yield 0
    return f"profile {mw.pm.name!r}, {col().card_count()} cards, {col().note_count()} notes"


def t_setup():
    # leftovers of an interrupted run
    if old := test_note_ids():
        col().remove_notes(old)
    deck_id()
    os.makedirs(WORK, exist_ok=True)
    col().media.write_data(MEDIA, PNG)
    yield 0
    return f"deck {DECK!r}"


def t_add_notes():
    before = col().note_count()
    add_basic("kioku front one", "kioku back one")
    add_basic("kioku front two", "kioku back two")
    add_basic(f'kioku picture <img src="{MEDIA}">', "kioku back picture")
    cloze = col().new_note(col().models.by_name("Cloze"))
    cloze["Text"] = "Kioku means {{c1::memory}}"
    cloze.tags = [TAG]
    col().add_note(cloze, deck_id())
    mw.reset()
    yield 0
    check(col().note_count() == before + 4, "note count did not grow by 4")
    check(len(test_note_ids()) == 4, f"{len(test_note_ids())} test notes, expected 4")
    return "4 notes (3 Basic, 1 Cloze, one with a picture)"


def t_add_window():
    """Add a note through the Add window: the text goes through the editor's
    page and back, then Add is pressed as its button does."""
    before = len(test_note_ids())
    mw.col.decks.select(deck_id())
    mw.onAddCard()
    yield Until(lambda: windows_of("NewAddCards") or windows_of("AddCards"), 15, "Add window")
    win = (windows_of("NewAddCards") or windows_of("AddCards"))[0]
    active = type(aqt.dialogs.activeWindow()).__name__
    check(active == type(win).__name__, f"activeWindow() is {active}")
    editor = win.editor
    web = editor.web
    fields = 0
    for _ in range(40):
        fields = yield Js(web, deep_js("return deep('*').filter(e => e.isContentEditable && e.tagName === 'ANKI-EDITABLE').length;"))
        if (fields or 0) >= 2:
            break
        yield 0.5
    check((fields or 0) >= 2, f"{fields} fields in the editor page")
    if not hasattr(editor, "note"):
        raise Skip("new editor (no note object to fill)")
    basic = col().models.by_name("Basic")["id"]
    # the note type a user picks in the window (it opens with the last one used)
    win.notetype_chooser.selected_notetype_id = basic
    yield Until(lambda: editor.note is not None and editor.note.mid == basic, 15, "a Basic note")
    editor.note["Front"] = "kioku added in window"
    editor.note["Back"] = "kioku window back"
    editor.note.tags = [TAG]
    editor.loadNote()
    shown = ""
    for _ in range(30):
        shown = yield Js(web, deep_js("return deep('anki-editable').map(e => e.innerText).join(' | ');"))
        if shown and "kioku added in window" in shown:
            break
        yield 0.5
    check(bool(shown) and "kioku added in window" in shown, f"editor page shows {shown!r:.80}")
    win.addButton.click()
    yield Until(lambda: len(test_note_ids()) == before + 1, 15, "the note in the collection")
    nid = col().find_notes('"Front:kioku added in window"')[0]
    card = col().get_card(col().get_note(nid).card_ids()[0])
    check(col().decks.name(card.did) == DECK, f"added to {col().decks.name(card.did)}")
    # the editor is empty again for the next note
    yield Until(lambda: editor.note is not None and not editor.note["Front"], 10, "an empty editor")
    close_window(win)
    yield Until(lambda: not windows_of(type(win).__name__), 10, "Add window closed")
    return "typed text reached the page, Add saved it to the deck, editor cleared"


def t_browse():
    browser = aqt.dialogs.open("Browser", mw)
    yield Until(lambda: windows_of("Browser"), 15, "Browse window")
    browser.search_for(f"tag:{TAG}")
    yield Until(lambda: browser.table.len() > 0, 15, "search results")
    rows = browser.table.len()
    expected = len(col().find_cards(f"tag:{TAG}")) if not browser.table.is_notes_mode() else len(test_note_ids())
    check(rows == expected, f"{rows} rows, expected {expected}")
    browser.search_for(f'tag:{TAG} "kioku front two"')
    yield Until(lambda: browser.table.len() == 1, 10, "one result")
    browser.table.select_all()
    editor = browser.editor
    current = (lambda: editor.note) if hasattr(editor, "note") else (
        lambda: editor.nid and col().get_note(editor.nid))
    yield Until(lambda: current() is not None and current()["Front"] == "kioku front two", 15,
                "editor shows the selected note")
    check(current()["Front"] == "kioku front two", f"editor has {current()['Front']!r}")
    shown = ""
    for _ in range(30):
        shown = yield Js(editor.web, deep_js("return deep('anki-editable').map(e => e.innerText).join(' | ');"))
        if shown and "kioku front two" in shown:
            break
        yield 0.5
    check(bool(shown) and "kioku front two" in shown, f"editor page shows {shown!r:.80}")
    # add the Add window over Browse: activeWindow() follows (26.09)
    mw.onAddCard()
    yield Until(lambda: windows_of("NewAddCards") or windows_of("AddCards"), 15, "Add window")
    active = type(aqt.dialogs.activeWindow()).__name__
    check(active in ("NewAddCards", "AddCards"), f"activeWindow() is {active}")
    close_extra_windows()
    yield Until(lambda: not windows_of("Browser"), 10, "Browse closed")
    return f"{rows} rows for tag:{TAG}, editor loads the selected note, Add over Browse is active"


def picture_card_id() -> int:
    nid = col().find_notes(f'tag:{TAG} "Front:kioku picture*"')[0]
    return col().get_note(nid).card_ids()[0]


def t_study():
    """Study the deck: the picture card comes first and shows its picture."""
    cid = picture_card_id()
    # position 0 comes before every other new card; nothing else moves
    col().sched.reposition_new_cards([cid], starting_from=0, step_size=1,
                                     randomize=False, shift_existing=False)
    col().decks.select(deck_id())
    mw.moveToState("overview")
    yield Until(lambda: mw.state == "overview", 10, "overview")
    yield 1
    text = yield body_text(mw.web)
    check(DECK in (text or ""), "overview doesn't show the deck")
    mw.moveToState("review")
    yield Until(lambda: mw.state == "review" and mw.reviewer.card is not None, 15, "a card")
    check(mw.reviewer.card.id == cid, "the picture card isn't first")
    text = None
    for _ in range(20):
        text = yield qa_text(mw.web)
        if text and "kioku picture" in text:
            break
        yield 0.5
    check(bool(text) and "kioku picture" in text, f"question shows {text!r:.80}")
    width = 0
    for _ in range(20):
        width = yield picture_width(mw.web)
        if width == 2:
            break
        yield 0.5
    check(width == 2, f"picture naturalWidth {width} (-1: no <img>, 0: not loaded)")
    return "question with its picture"


def t_review():
    check(mw.state == "review" and mw.reviewer.card, "not reviewing (study failed)")
    card = mw.reviewer.card
    before = revlog_count(card.id)
    mw.reviewer._showAnswer()
    yield Until(lambda: mw.reviewer.state == "answer", 10, "answer shown")
    text = None
    for _ in range(20):
        text = yield qa_text(mw.web)
        if text and "kioku back picture" in text:
            break
        yield 0.5
    check(bool(text) and "kioku back picture" in text, f"answer shows {text!r:.80}")
    mw.reviewer._answerCard(3)
    yield Until(lambda: revlog_count(card.id) == before + 1, 10, "review logged")
    yield Until(lambda: mw.reviewer.card is None or mw.reviewer.card.id != card.id, 10, "next card")
    return f"answered Good, revlog {before} -> {revlog_count(card.id)}, next card shown"


def t_undo():
    cid = picture_card_id()
    entries = revlog_count(cid)
    check(entries > 0, "nothing to undo (review failed)")
    mw.undo()
    yield Until(lambda: revlog_count(cid) == entries - 1, 10, "review undone")
    yield Until(lambda: mw.reviewer.card is not None and mw.reviewer.card.id == cid, 10,
                "the card back in the reviewer")
    mw.moveToState("deckBrowser")
    return "the review was undone, the card is shown again"


def t_review_picture():
    """The media server hands web views the collection's files."""
    url = f"{mw.serverURL()}{MEDIA}"
    box = in_thread(lambda: urllib.request.urlopen(url, timeout=10).read())
    yield Until(lambda: box, 15, "media server")
    if "error" in box:
        raise AssertionError(f"{url}: {box['error']}")
    check(box["value"] == PNG, "media server returned other bytes")
    return f"{len(PNG)} bytes from {url}"


def t_deck_browser():
    mw.moveToState("deckBrowser")
    yield Until(lambda: mw.state == "deckBrowser", 10, "deck list")
    yield 1
    text = yield body_text(mw.web)
    check(DECK in (text or ""), "deck list doesn't show the test deck")
    return "deck list shows the deck"


def t_stats():
    mw.onStats()
    yield Until(lambda: windows_of("NewDeckStats") or windows_of("DeckStats"), 15, "Statistics")
    win = (windows_of("NewDeckStats") or windows_of("DeckStats"))[0]
    web = web_in(win)
    yield Until(lambda: True, 1)
    svgs = 0
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        svgs = yield Js(web, "document.querySelectorAll('svg').length")
        if (svgs or 0) > 3:
            break
        yield 1
    check((svgs or 0) > 3, f"{svgs} graphs drawn")
    close_window(win)
    return f"{svgs} graphs"


def t_deck_options():
    import aqt.deckoptions

    aqt.deckoptions.display_options_for_deck_id(deck_id())
    yield Until(lambda: windows_of("DeckOptionsDialog"), 15, "Deck Options")
    win = windows_of("DeckOptionsDialog")[0]
    web = web_in(win)
    inputs = 0
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        inputs = yield Js(web, "document.querySelectorAll('input').length")
        if (inputs or 0) > 5:
            break
        yield 1
    check((inputs or 0) > 5, f"{inputs} inputs on the page")
    width = yield Js(web, "[document.documentElement.scrollWidth, window.innerWidth]")
    close_extra_windows()
    return f"{inputs} inputs, page/window width {width}"


def t_export_apkg():
    from anki.collection import DeckIdLimit, ExportAnkiPackageOptions

    path = os.path.join(WORK, "kioku-test.apkg")
    if os.path.exists(path):
        os.remove(path)
    count = col().export_anki_package(
        out_path=path,
        options=ExportAnkiPackageOptions(with_scheduling=True, with_deck_configs=False,
                                         with_media=True, legacy=False),
        limit=DeckIdLimit(deck_id()),
    )
    yield 0
    check(os.path.getsize(path) > 0, "empty package")
    check(count == len(test_note_ids()), f"exported {count} notes, expected {len(test_note_ids())}")
    return f"{count} notes, {os.path.getsize(path)} bytes"


def t_export_csv():
    from anki.collection import DeckIdLimit

    path = os.path.join(WORK, "kioku-test.txt")
    count = col().export_note_csv(out_path=path, limit=DeckIdLimit(deck_id()), with_html=True,
                                  with_tags=True, with_deck=True, with_notetype=True, with_guid=True)
    yield 0
    with open(path, encoding="utf8") as f:
        text = f.read()
    check("kioku front one" in text, "front text missing in the CSV")
    return f"{count} notes"


def t_export_window():
    mw.onExport()
    yield Until(lambda: any("Export" in type(w).__name__ for w in QApplication.topLevelWidgets() if w.isVisible()),
                15, "Export window")
    close_extra_windows()
    return "opens and closes"


def t_import_apkg():
    from anki.collection import ImportAnkiPackageOptions, ImportAnkiPackageRequest

    path = os.path.join(WORK, "kioku-test.apkg")
    check(os.path.exists(path), "no package (export failed)")
    count = len(test_note_ids())
    col().remove_notes(test_note_ids())
    col().media.trash_files([MEDIA])
    col().media.empty_trash()
    check(not test_note_ids(), "notes not removed")
    log = col().import_anki_package(ImportAnkiPackageRequest(
        package_path=path,
        options=ImportAnkiPackageOptions(merge_notetypes=False, with_scheduling=True,
                                         with_deck_configs=False)))
    mw.reset()
    yield 0
    check(len(test_note_ids()) == count, f"{len(test_note_ids())} notes back, expected {count}")
    check(col().media.have(MEDIA), "picture not imported")
    return f"{len(log.log.new)} new notes, picture restored"


def t_import_csv():
    from anki.collection import ImportCsvRequest

    path = os.path.join(WORK, "kioku-import.csv")
    with open(path, "w", encoding="utf8") as f:
        f.write("#separator:Comma\n#html:false\n#tags column:3\n")
        f.write("kioku csv one,csv back one,kiokutest\nkioku csv two,csv back two,kiokutest\n")
    meta = col().get_csv_metadata(path, None)
    meta.deck_id = deck_id()
    meta.global_notetype.id = col().models.by_name("Basic")["id"]
    del meta.global_notetype.field_columns[:]
    meta.global_notetype.field_columns.extend([1, 2])
    log = col().import_csv(ImportCsvRequest(path=path, metadata=meta))
    mw.reset()
    yield 0
    found = len(col().find_notes(f'tag:{TAG} "kioku csv*"'))
    check(found == 2, f"{found} CSV notes, expected 2")
    return f"{len(log.log.new)} new notes"


def t_import_window():
    """The import screen a user gets after picking a file."""
    from aqt.import_export import importing

    path = os.path.join(WORK, "kioku-test.apkg")
    importing.import_file(mw, path)
    yield Until(lambda: windows_of("ImportDialog"), 15, "Import window")
    win = windows_of("ImportDialog")[0]
    web = web_in(win)
    buttons = []
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        buttons = yield Js(web, deep_js("return deep('button').map(b => b.innerText.trim()).filter(Boolean);"))
        if buttons:
            break
        yield 1
    check(bool(buttons), "import page shows no buttons")
    close_extra_windows()
    return f"buttons: {', '.join(buttons[:4])}"


def t_check_database():
    notes, cards = len(test_note_ids()), len(col().find_cards(f"tag:{TAG}"))
    box = in_thread(lambda: col().fix_integrity())
    yield Until(lambda: box, 120, "Check Database")
    if "error" in box:
        raise box["error"]
    problems, ok = box["value"]
    # what it reports depends on the profile's data (a profile whose next
    # new card position is past 1,000,000 always gets a warning); the test's
    # notes and cards must come through intact
    check(len(test_note_ids()) == notes, f"{len(test_note_ids())} test notes, were {notes}")
    check(len(col().find_cards(f"tag:{TAG}")) == cards, "test cards changed")
    first = problems.strip().splitlines()[0][:100] if problems.strip() else "no problems"
    return f"finished: {first}"


def t_check_media():
    box = in_thread(lambda: col().media.check())
    yield Until(lambda: box, 120, "Check Media")
    if "error" in box:
        raise box["error"]
    out = box["value"]
    check(MEDIA not in out.missing, "test picture reported missing")
    return f"{len(out.missing)} missing, {len(out.unused)} unused"


def t_sync_server():
    from kioku import syncserver

    if syncserver.status().running:
        raise Skip("a sync server is already running (left alone)")
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    settings = syncserver.Settings(listen=syncserver.LOCAL, port=port, username="kiokutest",
                                   password="kiokutest-password")
    box = in_thread(lambda: syncserver.start(settings))
    yield Until(lambda: box, 20, "server start")
    status = box.get("value")
    try:
        check(status is not None and status.running, f"not running: {status and status.error}")
        check(syncserver.answers(), "/health doesn't answer")
    finally:
        done = in_thread(syncserver.stop)
        yield Until(lambda: done, 15, "server stop")
    with socket.socket() as s:
        closed = s.connect_ex(("127.0.0.1", port)) != 0
    check(closed, "port still open after stop")
    return f"port {port}: started, /health answered, stopped"


def t_python_packages():
    found, missing = [], []
    for mod in ("numpy", "PIL", "cryptography", "fitz", "orjson", "markdown", "bs4", "PyQt6.QtPdf"):
        try:
            __import__(mod)
            found.append(mod)
        except Exception as err:  # noqa: BLE001
            missing.append(f"{mod} ({type(err).__name__})")
    yield 0
    check(not missing, "missing: " + ", ".join(missing))
    return ", ".join(found)


def t_programs():
    from kioku import programs

    names = [n for n in ("ffmpeg", "mecab", "kakasi", "tesseract", "espeak-ng", "lame", "cwebp")
             if programs.which(n)]
    if not names:
        raise Skip("no bundled programs on this platform")
    import subprocess

    results = {}
    for name in names:
        arg = {"ffmpeg": "-version", "cwebp": "-version", "mecab": "--version", "kakasi": "-h"}.get(name, "--version")
        box = in_thread(lambda name=name, arg=arg: subprocess.run([name, arg], capture_output=True, timeout=30))
        yield Until(lambda box=box: box, 40, name)
        if "error" in box:
            results[name] = f"error {box['error']}"
        else:
            proc = box["value"]
            out = (proc.stdout or b"") + (proc.stderr or b"")
            results[name] = "ok" if out.strip() else f"no output (exit {proc.returncode})"
    bad = {k: v for k, v in results.items() if v != "ok"}
    check(not bad, f"{bad}")
    return ", ".join(results)


def t_https():
    if not NETWORK:
        raise Skip("network tests turned off")
    box = in_thread(lambda: urllib.request.urlopen("https://ankiweb.net/", timeout=20).status)
    yield Until(lambda: box, 30, "ankiweb.net")
    if "error" in box:
        raise AssertionError(f"https://ankiweb.net/: {box['error']}")
    return f"ankiweb.net answered {box['value']} (certificate verified)"


def t_cleanup():
    close_extra_windows()
    mw.moveToState("deckBrowser")
    if ids := test_note_ids():
        col().remove_notes(ids)
    for nid in col().find_notes(f"tag:{TAG}"):
        col().remove_notes([nid])
    did = col().decks.id_for_name(DECK)
    if did:
        col().decks.remove([did])
    col().media.trash_files([MEDIA])
    col().media.empty_trash()
    mw.reset()
    yield 0
    check(not col().find_notes(f"tag:{TAG}"), "test notes left")
    return "test deck, notes and picture removed"


TESTS = [
    ("version", t_version),
    ("profile", t_profile),
    ("setup", t_setup),
    ("add", t_add_notes),
    ("add-window", t_add_window),
    ("deck-list", t_deck_browser),
    ("browse", t_browse),
    ("study", t_study),
    ("review", t_review),
    ("undo", t_undo),
    ("media-server", t_review_picture),
    ("statistics", t_stats),
    ("deck-options", t_deck_options),
    ("export-apkg", t_export_apkg),
    ("export-csv", t_export_csv),
    ("export-window", t_export_window),
    ("import-apkg", t_import_apkg),
    ("import-csv", t_import_csv),
    ("import-window", t_import_window),
    ("check-database", t_check_database),
    ("check-media", t_check_media),
    ("sync-server", t_sync_server),
    ("python-packages", t_python_packages),
    ("programs", t_programs),
    ("https", t_https),
    ("cleanup", t_cleanup),
]
# always run: the notes most tests work with
ALWAYS = {"version", "setup", "add", "cleanup"}
# what a test needs to have run before it (for ONLY)
NEEDS = {
    "review": ["study"],
    "undo": ["study", "review"],
    "import-apkg": ["export-apkg"],
    "import-window": ["export-apkg"],
}


# --- runner ------------------------------------------------------------------


def write(record: dict) -> None:
    with open(RESULTS, "a", encoding="utf8") as f:
        f.write(json.dumps(record) + "\n")
    print("APPTEST", json.dumps(record), flush=True)


class Runner:
    def __init__(self) -> None:
        wanted = set(ONLY) | ALWAYS
        for name in ONLY:
            wanted.update(NEEDS.get(name, []))
        self.tests = [t for t in TESTS if not ONLY or t[0] in wanted]
        self.index = -1
        self.gen = None
        self.started = 0.0
        self.deadline = 0.0

    def next_test(self) -> None:
        self.index += 1
        if self.index >= len(self.tests):
            write({"done": True})
            return
        name, fn = self.tests[self.index]
        self.name = name
        self.started = time.monotonic()
        self.deadline = self.started + STEP_TIMEOUT
        try:
            self.gen = fn()
        except Exception as err:  # noqa: BLE001
            self.finish("fail", f"{type(err).__name__}: {err}")
            return
        self.resume(None)

    def finish(self, status: str, detail: str, tb: str = "") -> None:
        record = {"test": self.name, "status": status, "detail": detail,
                  "seconds": round(time.monotonic() - self.started, 1)}
        if tb:
            record["traceback"] = tb
        write(record)
        self.gen = None
        if status == "fail" and self.name not in ("cleanup",):
            close_extra_windows()
        QTimer.singleShot(300, self.next_test)

    def resume(self, value, error: BaseException | None = None) -> None:
        try:
            item = self.gen.throw(error) if error else self.gen.send(value)
        except StopIteration as stop:
            self.finish("pass", str(stop.value or ""))
            return
        except Skip as skip:
            self.finish("skip", str(skip))
            return
        except AssertionError as err:
            self.finish("fail", str(err))
            return
        except Exception as err:  # noqa: BLE001
            self.finish("fail", f"{type(err).__name__}: {err}", traceback.format_exc())
            return
        if time.monotonic() > self.deadline:
            self.gen.close()
            self.finish("fail", f"took longer than {STEP_TIMEOUT:.0f} s")
            return
        if isinstance(item, Until):
            self.wait_until(item, time.monotonic() + item.timeout)
        elif isinstance(item, Js):
            self.eval_js(item)
        else:
            QTimer.singleShot(int((item or 0) * 1000), lambda: self.resume(None))

    def wait_until(self, item: Until, deadline: float) -> None:
        try:
            ok = bool(item.cond())
        except Exception:  # noqa: BLE001
            ok = False
        if ok:
            QTimer.singleShot(0, lambda: self.resume(None))
        elif time.monotonic() > deadline:
            self.resume(None, AssertionError(f"timed out waiting for {item.what or 'a condition'}"))
        else:
            QTimer.singleShot(250, lambda: self.wait_until(item, deadline))

    def eval_js(self, item: Js) -> None:
        state = {"done": False}

        def got(value) -> None:
            if not state["done"]:
                state["done"] = True
                self.resume(value)

        def timeout() -> None:
            if not state["done"]:
                state["done"] = True
                self.resume(None, AssertionError(f"no answer from the web view: {item.code[-60:]!r}"))

        QTimer.singleShot(int(item.timeout * 1000), timeout)
        item.web.evalWithCallback(item.code, got)


os.makedirs(WORK, exist_ok=True)
if os.path.exists(RESULTS):
    os.remove(RESULTS)
_runner = Runner()
QTimer.singleShot(100, _runner.next_test)
print("apptest started:", len(_runner.tests), "tests")
