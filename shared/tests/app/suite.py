# Kioku's in-app test suite: real user flows in the running app (iOS, Android,
# the iOS Simulator), sent through the development command channel
# (shared/python/kioku/devtools.py) by shared/tools/apptest.py, which prepends
#
#   EXPECTED_VERSION = "26.09.4"   # Anki version the build must report
#   EXPECTED_RUNTIME = {...}       # Python, Qt, PyQt the release pins (versions.env)
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
    EXPECTED_RUNTIME = {}
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
    # add-ons expect desktop Anki's Python and Qt (AnkiHub failed on 3.14)
    runtime = {
        "PYTHON_FULL_VERSION": pyplatform.python_version(),
        "QT_VERSION": QT_VERSION_STR,
        "PYQT6_VERSION": PYQT_VERSION_STR,
    }
    for key, want in globals().get("EXPECTED_RUNTIME", {}).items():
        check(not want or runtime[key] == want, f"{info}; expected {key} {want}")
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


# Helpers for the editor page, kept on window between evaluations. Buttons are
# found by their tooltip (translated: the titles come from Python's tr).
EDITOR_JS = """(() => { window.__kt = {
  eds: () => [...document.querySelectorAll('.rich-text-editable')]
      .map(h => h.shadowRoot && h.shadowRoot.querySelector('anki-editable')).filter(Boolean),
  field() { return this.eds()[0]; },
  // focus the field. An Android WebView that was never tapped doesn't have
  // the focus, and its page then gets no focus events from focus(): the
  // editor's buttons stayed disabled. Send the events a tap would have.
  focus() { const e = this.field(); e.focus();
      if (!document.hasFocus()) {
          e.dispatchEvent(new FocusEvent('focus'));
          e.dispatchEvent(new FocusEvent('focusin', {bubbles: true, composed: true}));
      } },
  set(html) { const e = this.field(); this.focus(); e.innerHTML = html;
      e.dispatchEvent(new Event('input', {bubbles: true})); },
  text() { return document.createTreeWalker(this.field(), NodeFilter.SHOW_TEXT).nextNode(); },
  // the selection as Anki gets it (cross-browser.ts): the shadow root's
  // where there is one (Blink), else the document's (WebKit)
  sel() { const r = this.field().getRootNode();
      return r.getSelection ? r.getSelection() : document.getSelection(); },
  // move the focus to the second field, sending the first one's blur where
  // focus() sends none (an Android WebView that was never tapped): before
  // the selection moves, as a real blur comes
  away() { const e = this.field(), o = this.eds()[1];
      if (document.hasFocus()) return o.focus();
      e.dispatchEvent(new FocusEvent('blur'));
      e.dispatchEvent(new FocusEvent('focusout', {bubbles: true, composed: true}));
      o.focus();
      o.dispatchEvent(new FocusEvent('focus')); },
  caret() { const s = this.sel();
      return s.rangeCount ? {node: s.focusNode.nodeName, offset: s.focusOffset} : null; },
  // select characters a..b of the field's first text node
  select(a, b) { const t = this.text(); this.focus(); this.sel().setBaseAndExtent(t, a, t, b); },
  click(title) {
      const b = [...document.querySelectorAll('button')].find(b => (b.title || '').startsWith(title));
      if (!b) return 'no button ' + title;
      b.click(); return 'ok'; },
  item(label) {
      const i = [...document.querySelectorAll('button, .dropdown-item')]
          .find(b => (b.textContent || '').trim().startsWith(label));
      if (!i) return 'no menu item ' + label;
      i.click(); return 'ok'; },
  html() { return this.field().innerHTML.replace(/<br>$/, ''); },
  state() { const s = this.sel();
      return {html: this.html(), selected: String(s),
              range: s.rangeCount ? s.getRangeAt(0).startContainer.nodeName : '',
              anchor: s.anchorNode ? s.anchorNode.nodeName : ''}; },
}; return window.__kt.eds().length; })()"""


def kt(web: AnkiWebView, call: str) -> Js:
    return Js(web, f"window.__kt.{call}")


def open_editor():
    """The Add window, with EDITOR_JS on its editor page."""
    mw.col.decks.select(deck_id())
    mw.onAddCard()
    yield Until(lambda: windows_of("NewAddCards") or windows_of("AddCards"), 15, "Add window")
    win = (windows_of("NewAddCards") or windows_of("AddCards"))[0]
    web = win.editor.web
    chooser = getattr(win, "notetype_chooser", None)
    if chooser is None:
        raise Skip("new editor (no note type chooser)")
    first_notetype = chooser.selected_notetype_id
    basic = col().models.by_name("Basic")["id"]
    chooser.selected_notetype_id = basic
    yield Until(lambda: win.editor.note is not None and win.editor.note.mid == basic, 15, "a Basic note")
    fields = 0
    for _ in range(40):
        fields = yield Js(web, EDITOR_JS)
        if (fields or 0) >= 2:
            break
        yield 0.5
    check((fields or 0) >= 2, f"{fields} fields in the editor page")
    return win, web, chooser, first_notetype


def close_editor(win, web, chooser, first_notetype):
    """Empty the field and close the Add window, as open_editor found it."""
    yield kt(web, "set('')")
    yield 0.3
    win.editor.note.fields[0] = ""
    chooser.selected_notetype_id = first_notetype
    yield 0.5
    close_window(win)
    yield Until(lambda: not windows_of(type(win).__name__), 10, "Add window closed")


def t_editor_formatting():
    """The editor's toolbar on a selection inside a field. The fields live in
    shadow roots, whose selection WebKit (iOS) reported on the shadow host:
    the surround buttons did nothing and MathJax lost the text (issue #17,
    kioku.webscripts.SHADOW_SELECTION)."""
    from aqt.utils import tr

    win, web, chooser, first_notetype = yield from open_editor()

    def apply(html: str, title: str, menu_item: str = ""):
        """Put html in the first field, select "hello", press the button."""
        yield kt(web, f"set({json.dumps(html)})")
        yield 0.3
        yield kt(web, "select(0, 5)")
        yield 0.1
        clicked = yield kt(web, f"click({json.dumps(title)})")
        check(clicked == "ok", str(clicked))
        if menu_item:
            yield 0.4
            clicked = yield kt(web, f"item({json.dumps(menu_item)})")
            check(clicked == "ok", str(clicked))
        yield 0.4
        return (yield kt(web, "state()")) or {}

    done = []
    for tag, title in [
        ("b", tr.editing_bold_text()),
        ("i", tr.editing_italic_text()),
        ("u", tr.editing_underline_text()),
        ("sup", tr.editing_superscript()),
        ("sub", tr.editing_subscript()),
    ]:
        state = yield from apply("hello world", title)
        want = f"<{tag}>hello</{tag}> world"
        check(state.get("html") == want, f"{tag}: field is {state.get('html')!r}, expected {want!r}")
        check(state.get("selected") == "hello", f"{tag}: selection is {state.get('selected')!r} after the button")
        check(state.get("range") == "#text", f"{tag}: getRangeAt(0) starts in {state.get('range')!r}, not the text")
        # pressing it again on the same selection removes it
        yield kt(web, f"click({json.dumps(title)})")
        yield 0.4
        html = yield kt(web, "html()")
        check(html == "hello world", f"{tag} off: field is {html!r}")
        done.append(tag)

    for name, prop, title in [
        ("text color", "color", tr.editing_text_color()),
        ("highlight", "background-color", tr.editing_text_highlight_color()),
    ]:
        state = yield from apply("hello world", title)
        html = state.get("html") or ""
        check(html.startswith('<span style="' + prop + ":") and html.endswith(">hello</span> world"),
              f"{name}: field is {html!r}")
        done.append(name)

    state = yield from apply("<b>hello</b> world", tr.editing_remove_formatting())
    check(state.get("html") == "hello world", f"remove formatting: field is {state.get('html')!r}")
    done.append("remove formatting")

    state = yield from apply("hello world", tr.editing_equations(), tr.editing_mathjax_inline())
    check('data-mathjax="hello"' in (state.get("html") or ""),
          f"MathJax inline: field is {(state.get('html') or '')[:120]!r}")
    done.append("MathJax")

    # underline at a caret, then type: the typed text is underlined. The
    # keystroke is the beforeinput event Anki handles (it inserts the text
    # itself); execCommand fires none in Blink.
    yield kt(web, "set('hello world')")
    yield 0.3
    yield kt(web, "select(11, 11)")
    yield 0.1
    yield kt(web, f"click({json.dumps(tr.editing_underline_text())})")
    yield 0.3
    yield kt(web, "field().dispatchEvent(new InputEvent('beforeinput', "
                  "{inputType: 'insertText', data: 'X', bubbles: true, cancelable: true}))")
    yield 0.4
    html = yield kt(web, "html()")
    check(html == "hello world<u>X</u>", f"underline at the caret, then typing: field is {html!r}")
    done.append("caret")

    # the cloze button wraps the selection (a Cloze note's text field)
    cloze = col().models.by_name("Cloze")
    if cloze:
        chooser.selected_notetype_id = cloze["id"]
        yield Until(lambda: win.editor.note is not None and win.editor.note.mid == cloze["id"], 15, "a Cloze note")
        for _ in range(20):
            fields = yield Js(web, EDITOR_JS)
            if fields:
                break
            yield 0.5
        state = yield from apply("hello world", tr.editing_cloze_deletion())
        check((state.get("html") or "").startswith("{{c1::hello}}"), f"cloze: field is {state.get('html')!r}")
        done.append("cloze")

    yield from close_editor(win, web, chooser, first_notetype)
    return ", ".join(done)


# a dozen buttons, each a few round trips to the page: a minute on a slow
# emulator
t_editor_formatting.timeout = 90.0


def t_editor_caret():
    """The caret stays where it was when a field gets the focus back without
    a tap (Tab from the next field, back from a dialog). WebKit (iOS) empties
    the selection before the field's blur, where Anki saves it: the caret
    went to the end of the field (kioku.webscripts.SHADOW_SELECTION)."""
    win, web, chooser, first_notetype = yield from open_editor()
    yield kt(web, "set('hello world')")
    yield 0.3
    yield kt(web, "select(3, 3)")
    yield 0.2
    yield kt(web, "away()")
    yield 0.4
    yield kt(web, "focus()")
    yield 0.4
    caret = (yield kt(web, "caret()")) or {}
    check(caret == {"node": "#text", "offset": 3},
          f"caret after the field got the focus back is {caret}, expected offset 3 in the text")
    # and a selection made backwards
    yield kt(web, "select(8, 2)")
    yield 0.2
    yield kt(web, "away()")
    yield 0.4
    yield kt(web, "focus()")
    yield 0.4
    state = (yield kt(web, "state()")) or {}
    caret = (yield kt(web, "caret()")) or {}
    check(state.get("selected") == "llo wo" and caret.get("offset") == 2,
          f"selection after the field got the focus back is {state.get('selected')!r}, focus at {caret}")
    yield from close_editor(win, web, chooser, first_notetype)
    return "caret and a backward selection kept"


def t_bottom_buttons():
    """TestFlight (iPhone SE): the deck list's bottom bar buttons (Get
    Shared, Create Deck, Import File) were desktop-sized, 32px tall with
    11px text: on a touch screen they are at least 44px tall and the bar
    shows them whole (webscripts.PHONE_CSS)."""
    mw.moveToState("deckBrowser")
    yield Until(lambda: mw.state == "deckBrowser", 10, "deck list")
    js = ("JSON.stringify({coarse: matchMedia('(pointer: coarse)').matches,"
          " body: document.body.scrollHeight, buttons: [...document.querySelectorAll("
          "'#outer > #header button')].map(b => [b.textContent,"
          " Math.round(b.getBoundingClientRect().height), parseFloat(getComputedStyle(b).fontSize)])})")
    info = None
    for _ in range(20):
        info = json.loads((yield Js(mw.bottomWeb, js)) or "null")
        if info and info["buttons"]:
            break
        yield 0.5
    check(bool(info and info["buttons"]), f"no bottom bar buttons: {info}")
    if not info["coarse"]:
        raise Skip("no touch screen")
    small = [b for b in info["buttons"] if b[1] < 44 or b[2] < 14]
    check(not small, f"buttons too small [text, height, font px]: {small}")
    yield Until(lambda: mw.bottomWeb.height() >= info["body"], 5, "bottom bar shows the buttons whole")
    return f"{len(info['buttons'])} buttons, {info['buttons'][0][1]}px tall"


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


def t_browse_columns():
    """View › Columns shows and hides the browser's columns (issue #20: the
    header's context menu is out of a touch's reach)."""
    browser = aqt.dialogs.open("Browser", mw)
    yield Until(lambda: windows_of("Browser"), 15, "Browse window")
    table = browser.table
    model = table._model
    menus = [a.menu() for a in browser.form.menuqt_accel_view.actions()
             if a.menu() is not None and a.menu().title() == "Columns"]
    check(len(menus) == 1, f"{len(menus)} Columns menus in View")
    menu = menus[0]
    menu.aboutToShow.emit()
    rows = menu.actions()
    check(len(rows) == len(model.columns), f"{len(rows)} rows for {len(model.columns)} columns")
    key = next((k for k in model.columns if model.active_column_index(k) is None), None)
    check(key is not None, "every column is shown")
    action = rows[list(model.columns).index(key)]
    check(action.text() == table._state.column_label(model.columns[key]),
          f"row {action.text()!r} for column {key}")
    check(not action.isChecked(), "a hidden column's row is checked")
    try:
        action.trigger()
        yield 0.3
        check(model.active_column_index(key) is not None, f"{key} not shown after its row")
        check(action.isChecked(), "row not checked after showing the column")
        action.trigger()
        yield 0.3
        check(model.active_column_index(key) is None, f"{key} still shown after its row")
        # toggled elsewhere (the header's menu): the row follows
        table._on_column_toggled(True, key)
        yield 0.3
        check(action.isChecked(), "row not checked after the header showed the column")
    finally:
        if model.active_column_index(key) is not None:
            table._on_column_toggled(False, key)
    close_extra_windows()
    yield Until(lambda: not windows_of("Browser"), 10, "Browse closed")
    return f"{len(rows)} columns in View › Columns; {key} shown and hidden"


def t_numpad_done():
    """iPhone: number fields (Custom Study's limit) show the number pad,
    which has no Return key and covered the dialog's OK: a Done bar above it
    closes the keyboard and keeps the number (donebar.py)."""
    if sys.platform != "ios":
        raise Skip(sys.platform)
    import kioku_platform.donebar as donebar
    from aqt.customstudy import CustomStudy
    from aqt.qt import QGuiApplication, QInputMethodQueryEvent, Qt
    from rubicon.objc import ObjCClass

    from kioku_platform.webview import prop

    if donebar._filter is None:
        raise Skip("not an iPhone")
    col().decks.select(deck_id())
    QTimer.singleShot(0, lambda: CustomStudy.fetch_data_and_show(mw))
    yield Until(lambda: windows_of("CustomStudy"), 10, "Custom Study")
    dialog = windows_of("CustomStudy")[0]
    try:
        spin = dialog.form.spin
        spin.setFocus()
        yield 0.3
        query = QInputMethodQueryEvent(
            Qt.InputMethodQuery.ImPlatformData | Qt.InputMethodQuery.ImHints
        )
        QApplication.sendEvent(spin, query)
        data = query.value(Qt.InputMethodQuery.ImPlatformData)
        check(isinstance(data, dict) and donebar.ACCESSORY_KEY in data,
              f"no Done bar in the number field's platform data: {data!r}")
        hints = query.value(Qt.InputMethodQuery.ImHints)
        check(int(getattr(hints, "value", hints)) & Qt.InputMethodHint.ImhDigitsOnly.value,
              f"hints {hints!r} are not digits only")
        im = QGuiApplication.inputMethod()
        im.show()
        yield Until(lambda: im.isVisible(), 5, "keyboard")
        spin.lineEdit().setText("7")
        prop(ObjCClass("UIApplication"), "sharedApplication").sendAction_to_from_forEvent_(
            donebar.SEL("done:"), donebar._filter._target, None, None
        )
        yield Until(lambda: not im.isVisible(), 5, "keyboard closed by Done")
        check(QApplication.focusWidget() is not spin, "the number field kept the focus")
        check(spin.value() == 7, f"value {spin.value()} after Done, not 7")
    finally:
        dialog.reject()
    yield Until(lambda: not windows_of("CustomStudy"), 10, "Custom Study closed")
    return "Done bar on the number pad closes it; the number stays"


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


def t_review_focus():
    """Issue #24: after a card is answered from the bottom bar, the next
    card's page has the keyboard focus, so its {{type:}} box takes typing."""
    sub = col().decks.id(f"{DECK}::Focus")
    model = col().models.by_name("Basic (type in the answer)")
    nids = []
    for i in (1, 2):
        note = col().new_note(model)
        note["Front"], note["Back"] = f"kioku focus {i}", f"answer {i}"
        note.tags = [TAG]
        col().add_note(note, sub)
        nids.append(note.id)
    focus_js = ("JSON.stringify([document.hasFocus(),"
                " document.activeElement ? document.activeElement.id : ''])")
    try:
        col().decks.select(sub)
        mw.moveToState("overview")
        yield Until(lambda: mw.state == "overview", 10, "overview")
        yield 1
        # as a tap on Study Now: the page has the keyboard focus
        mw.web.page()._web.focus(True)
        yield 0.5
        mw.moveToState("review")
        yield Until(lambda: mw.state == "review" and mw.reviewer.card is not None
                    and mw.reviewer.card.nid in nids, 15, "a type-in card")
        first = mw.reviewer.card.id
        main = None
        for _ in range(20):
            main = json.loads((yield Js(mw.web, focus_js)) or "null")
            if main == [True, "typeans"]:
                break
            yield 0.5
        check(main == [True, "typeans"], f"first card [hasFocus, activeElement] = {main}")
        # a tap on the bottom bar's buttons leaves the keyboard focus there
        mw.bottomWeb.page()._web.focus(True)
        yield 0.5
        mw.reviewer._showAnswer()
        yield Until(lambda: mw.reviewer.state == "answer", 10, "answer shown")
        yield 0.5
        mw.bottomWeb.page()._web.focus(True)
        yield 0.5
        mw.reviewer._answerCard(3)
        yield Until(lambda: mw.reviewer.card is not None and mw.reviewer.card.id != first
                    and mw.reviewer.state == "question", 10, "the next card")
        main = bottom = None
        for _ in range(20):
            main = json.loads((yield Js(mw.web, focus_js)) or "null")
            bottom = json.loads((yield Js(mw.bottomWeb, focus_js)) or "null")
            if main == [True, "typeans"] and bottom and not bottom[0]:
                break
            yield 0.5
        check(main == [True, "typeans"],
              f"card page [hasFocus, activeElement] = {main}, bottom bar = {bottom}")
        check(bool(bottom) and not bottom[0], f"the bottom bar kept the focus: {bottom}")
        # iOS: WebKit takes typing (shows the keyboard) only once it started
        # its input session; a script's focus() alone left the box focused
        # in the page, yet the keys went elsewhere
        typing = getattr(mw.web.page()._web, "typing_focus", None)
        if typing is not None:
            ok = False
            for _ in range(20):
                ok = typing()
                if ok:
                    break
                yield 0.5
            check(ok, "the next card's typing box has the page's focus, but WebKit"
                  " started no input session (no keyboard, keys go elsewhere)")
            # type as the on-screen keyboard does (its Return is a key
            # event, not text: not emulated here)
            web = mw.web.page()._web
            web.type_text("kioku")
            typed = ""
            for _ in range(20):
                typed = yield Js(mw.web, "document.getElementById('typeans').value")
                if typed == "kioku":
                    break
                yield 0.25
            check(typed == "kioku", f"typing reached the box: {typed!r}")
    finally:
        mw.moveToState("deckBrowser")
        col().remove_notes(nids)
        col().decks.remove([sub])
    return "the next card's typing box has the keyboard focus"


def t_review_keys():
    """A hardware keyboard in the reviewer on Android: after a page was
    tapped, Space and 1-4 reach Anki's shortcuts, a key no shortcut takes
    reaches the card's keydown listener, and the {{type:}} box keeps every
    key (KiokuKeys)."""
    if sys.platform != "android":
        raise Skip("Android's key routing (iOS: kioku_platform.keys)")
    from aqt import dialogs
    from kioku_platform import bridge

    SPACE, KEY_3, KEY_E, KEY_J = 62, 10, 33, 38

    def press(code: int) -> None:
        bridge.call("keys.test", code=code, down=True)
        bridge.call("keys.test", code=code, down=False)

    def editing():
        return bridge.call("keys.editing")

    def editors() -> list:
        return [d[1] for name, d in dialogs._dialogs.items()
                if name in ("EditCurrent", "NewEditCurrent") and d[1] is not None]

    sub = col().decks.id(f"{DECK}::Keys")
    model = col().models.by_name("Basic (type in the answer)")
    nids = []
    for i in (1, 2):
        note = col().new_note(model)
        note["Front"], note["Back"] = f"kioku keys {i}", f"answer {i}"
        note.tags = [TAG]
        col().add_note(note, sub)
        nids.append(note.id)
    try:
        col().decks.select(sub)
        mw.moveToState("overview")
        yield Until(lambda: mw.state == "overview", 10, "overview")
        yield 1
        mw.web.page()._web.focus(True)  # as a tap on Study Now
        yield 0.5
        mw.moveToState("review")
        yield Until(lambda: mw.state == "review" and mw.reviewer.card is not None
                    and mw.reviewer.card.nid in nids, 15, "a type-in card")
        first = mw.reviewer.card.id
        yield Until(lambda: editing() is True, 10, "the typing box focused")
        # the typing box keeps every key: "e" is typed, the editor stays shut
        press(KEY_E)
        typed = ""
        for _ in range(20):
            typed = yield Js(mw.web, "document.getElementById('typeans').value")
            if typed == "e":
                break
            yield 0.25
        check(typed == "e", f"typing box holds {typed!r}")
        check(not editors(), "'e' opened the editor")
        # outside a text field a key no shortcut takes reaches the card
        yield Js(mw.web, "window.__kiokuKeys=[];document.addEventListener('keydown',"
                         "function(e){window.__kiokuKeys.push(e.key);});"
                         "document.activeElement.blur();")
        yield Until(lambda: editing() is False, 10, "the typing box left")
        press(KEY_J)
        keys: list = []
        for _ in range(20):
            keys = json.loads((yield Js(mw.web, "JSON.stringify(window.__kiokuKeys)")) or "[]")
            if "j" in keys:
                break
            yield 0.25
        check("j" in keys, f"the card's keydown listener got {keys}")
        # Anki's shortcuts after a tap on the bottom bar
        mw.bottomWeb.page()._web.focus(True)
        yield 0.5
        press(SPACE)
        yield Until(lambda: mw.reviewer.state == "answer", 10, "Space showing the answer")
        keys = json.loads((yield Js(mw.web, "JSON.stringify(window.__kiokuKeys)")) or "[]")
        check(" " not in keys, f"the page got Space as well: {keys}")
        mw.bottomWeb.page()._web.focus(True)
        yield 0.5
        press(KEY_3)
        yield Until(lambda: mw.reviewer.card is not None and mw.reviewer.card.id != first
                    and mw.reviewer.state == "question", 10, "3 answering Good")
    finally:
        for editor in editors():
            editor.close()
        mw.moveToState("deckBrowser")
        col().remove_notes(nids)
        col().decks.remove([sub])
    return "Space and 3 answer, j reaches the card, the typing box keeps e"


def t_card_keys():
    """Issue #31, iOS: a key pressed outside a text field goes to Qt first
    (kioku_platform.keys) and WebKit takes no keys then; one that no
    shortcut took reaches the card's keydown listener with no element
    focused, as on desktop Anki."""
    import kioku_platform
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication

    if not getattr(kioku_platform.WebView, "KEYS_AS_SCRIPT", False):
        raise Skip("keys reach the page natively (Android: review-keys)")
    sub = col().decks.id(f"{DECK}::CardKeys")
    note = col().new_note(col().models.by_name("Basic"))
    note["Front"], note["Back"] = "kioku card keys", "answer"
    note.tags = [TAG]
    col().add_note(note, sub)
    try:
        col().decks.select(sub)
        mw.moveToState("review")
        yield Until(lambda: mw.state == "review" and mw.reviewer.card is not None
                    and mw.reviewer.card.nid == note.id, 15, "the card")
        yield 1
        yield Js(mw.web, "window.__kiokuKeys=[];['keydown','keypress','keyup'].forEach("
                         "function(t){document.addEventListener(t,function(e){"
                         "window.__kiokuKeys.push(t+':'+e.key+':'+e.keyCode);});});"
                         "if(document.activeElement)document.activeElement.blur();")
        mw.web.setFocus()
        none = Qt.KeyboardModifier.NoModifier
        for key, text in ((Qt.Key.Key_J, "j"), (Qt.Key.Key_Left, "")):
            for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                QApplication.sendEvent(mw.web, QKeyEvent(kind, key, none, text))
        want = ["keydown:j:74", "keypress:j:74", "keyup:j:74",
                "keydown:ArrowLeft:37", "keyup:ArrowLeft:37"]
        got = None
        for _ in range(20):
            got = json.loads((yield Js(mw.web, "JSON.stringify(window.__kiokuKeys)")) or "null")
            if got == want:
                break
            yield 0.25
        check(got == want, f"the card's listener got {got}")
        check(mw.reviewer.card.nid == note.id and mw.reviewer.state == "question",
              "a key handed to the page also acted in Anki")
    finally:
        mw.moveToState("deckBrowser")
        col().remove_notes([note.id])
        col().decks.remove([sub])
    return "a key no shortcut took reached the card's keydown listener"


class _PadRecorder:
    """Records what the platform reports to kioku.gamepad, instead of
    running actions."""

    def __init__(self, pads) -> None:
        self.pads = pads
        self.events: list = []
        for name in ("button", "axes", "connected"):
            setattr(pads, name, self._record(name))

    def _record(self, name):
        return lambda *args: self.events.append((name, *args))

    def restore(self) -> None:
        for name in ("button", "axes", "connected"):
            self.pads.__dict__.pop(name, None)


def _gamepads():
    from kioku import gamepad

    pads = gamepad.instance()
    if pads is None:
        raise Skip("gamepad support didn't start")
    return gamepad, pads


def t_gamepad():
    """Study with a controller's default buttons: presses go through
    kioku.gamepad into Anki's own shortcuts."""
    gamepad, pads = _gamepads()
    saved = pads.settings
    pads.settings = gamepad.Settings.from_dict({"version": gamepad.VERSION})

    def tap(name: str) -> None:
        pads.button(name, True, "test")
        pads.button(name, False, "test")

    try:
        did = deck_id()
        col().decks.select(did)
        mw.moveToState("deckBrowser")
        yield Until(lambda: mw.state == "deckBrowser", 10, "deck list")
        yield 1
        pads.actions.deck_id = None
        tap("Down")  # the first press shows the highlight on the current deck
        yield Until(lambda: pads.actions.deck_id == str(did), 10, "the test deck highlighted")
        tap("A")
        yield Until(lambda: mw.state == "overview", 10, "A: the deck's overview")
        yield 1
        tap("A")
        yield Until(lambda: mw.state == "review" and mw.reviewer.card is not None, 15, "A: studying")
        yield Until(lambda: mw.reviewer.state == "question", 10, "the question")
        card = mw.reviewer.card
        before = revlog_count(card.id)
        tap("B")  # Again: only on the answer side
        yield 1
        check(mw.reviewer.state == "question" and revlog_count(card.id) == before,
              "B on the question did something")
        tap("A")
        yield Until(lambda: mw.reviewer.state == "answer", 10, "A: the answer")
        tap("B")
        yield Until(lambda: revlog_count(card.id) == before + 1, 10, "B: answered Again")
        tap("L1")
        yield Until(lambda: revlog_count(card.id) == before, 10, "L1: undone")
        yield Until(lambda: mw.reviewer.card is not None and mw.reviewer.card.id == card.id, 10,
                    "the card back")
        tap("View")
        yield Until(lambda: mw.state == "overview", 10, "View: back to the overview")
        tap("B")
        yield Until(lambda: mw.state == "deckBrowser", 10, "B: back to the deck list")
    finally:
        pads.settings = saved
    return "deck list → overview → study → answer → Again → undo → back"


def t_gamepad_native():
    """A controller's events through the platform layer: Android key and
    joystick events through KiokuActivity, iOS Apple's virtual controller."""
    gamepad, pads = _gamepads()
    if not pads.settings.enabled:
        raise Skip("gamepads are turned off (Preferences › Advanced)")
    recorder = _PadRecorder(pads)
    try:
        if sys.platform == "android":
            result = yield from _gamepad_android(recorder)
        elif sys.platform == "ios":
            result = yield from _gamepad_ios(recorder)
        else:
            raise Skip(sys.platform)
    finally:
        recorder.restore()
    return result


def _gamepad_android(recorder):
    from kioku_platform import bridge

    SOURCE_GAMEPAD, SOURCE_KEYBOARD = 0x401, 0x101
    BUTTON_A, DPAD_DOWN, BUTTON_START = 96, 20, 108

    def key(code: int, down: bool, source: int = SOURCE_GAMEPAD) -> bool:
        return bridge.call("gamepad.test", kind="key", code=code, down=down, source=source)

    check(key(BUTTON_A, True) and key(BUTTON_A, False), "button A not taken")
    check(key(BUTTON_START, True) and key(BUTTON_START, False), "Start not taken")
    check(key(DPAD_DOWN, True) and key(DPAD_DOWN, False), "the controller's d-pad not taken")
    check(not key(DPAD_DOWN, True, SOURCE_KEYBOARD), "a keyboard's arrow was taken")
    check(bridge.call("gamepad.test", kind="motion", axes={
        "AXIS_X": 0.0, "AXIS_Y": 1.0, "AXIS_RZ": -0.6, "AXIS_HAT_X": -1.0, "AXIS_LTRIGGER": 0.8,
    }), "joystick motion not taken")
    expected = [
        ("button", "A", True, "key"), ("button", "A", False, "key"),
        ("button", "Menu", True, "key"), ("button", "Menu", False, "key"),
        ("button", "Down", True, "key"), ("button", "Down", False, "key"),
        ("axes", "left", 0.0, 1.0), ("axes", "right", 0.0, -0.6),
        ("axes", "hat", -1.0, 0.0), ("axes", "triggers", 0.8, 0.0),
    ]
    yield Until(lambda: len(recorder.events) >= len(expected), 10, "the events in Python")
    bridge.call("gamepad.test", kind="motion", axes={"AXIS_X": 0.0})  # sticks back
    yield 0.5
    check(recorder.events[:len(expected)] == expected, f"got {recorder.events[:len(expected)]}")
    return "buttons, d-pad, sticks, hat and trigger reached Python; keyboard left alone"


def _gamepad_ios(recorder):
    import ctypes

    from rubicon.objc import ObjCClass, ObjCInstance
    from rubicon.objc.runtime import load_library, send_message

    from kioku_platform import gamepad as ios_pads
    from kioku_platform.webview import prop

    lib = load_library("GameController")

    def const(name: str):
        return ObjCInstance(ctypes.c_void_p(ctypes.c_void_p.in_dll(lib, name).value))

    try:
        virtual_cls = ObjCClass("GCVirtualController")
    except NameError:
        raise Skip("no GCVirtualController (iOS 15+)")
    button_a, button_b = const("GCInputButtonA"), const("GCInputButtonB")
    config = ObjCClass("GCVirtualControllerConfiguration").alloc().init()
    config.setElements_(ObjCClass("NSSet").setWithArray_([button_a, button_b, const("GCInputDirectionPad")]))
    virtual = virtual_cls.virtualControllerWithConfiguration_(config)
    before = set(ios_pads._pads)
    virtual.connectWithReplyHandler_(None)
    try:
        yield Until(lambda: any(e[0] == "connected" and e[3] for e in recorder.events), 10,
                    "the virtual controller connected")
        check(len(set(ios_pads._pads) - before) == 1, "Kioku didn't watch the virtual controller")
        detail = "connected"
        can_press = send_message(virtual, "respondsToSelector:", _sel("setValue:forButtonElement:"),
                                 restype=ctypes.c_bool, argtypes=[ctypes.c_void_p])
        if can_press:  # iOS 17+
            for value in (1.0, 0.0):
                send_message(virtual, "setValue:forButtonElement:", value, button_a.ptr,
                             restype=None, argtypes=[ctypes.c_double, ctypes.c_void_p])
                yield 0.3
            yield Until(lambda: ("button", "A", False) in [e[:3] for e in recorder.events], 5,
                        "button A down and up")
            check(("button", "A", True) in [e[:3] for e in recorder.events], "no press of A")
            detail += ", A pressed and released through Kioku's handler"
        else:
            # iOS 15/16: no way to press; read a snapshot through the handler
            pad = list(ios_pads._pads.values())[-1]
            snap = ios_pads._Pad(ObjCInstance(send_message(
                pad.controller, "capture", restype=ctypes.c_void_p, argtypes=[])))
            element = prop(snap.pad, "buttonA")
            send_message(element, "setValue:", 1.0, restype=None, argtypes=[ctypes.c_float])
            snap._changed(None, element)
            snap.close()
            check(("button", "A", True) in [e[:3] for e in recorder.events], "snapshot A not read")
            detail += ", a snapshot's A read by Kioku's handler"
    finally:
        virtual.disconnect()
    yield Until(lambda: any(e[0] == "connected" and not e[3] for e in recorder.events), 10,
                "the virtual controller disconnected")
    return detail


def _sel(name: str) -> int:
    import ctypes

    objc = ctypes.CDLL("/usr/lib/libobjc.dylib")
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    return objc.sel_registerName(name.encode())


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


def _deck_name_size() -> Js:
    """[on-screen height of the test deck's name, page width beyond the
    window]: CSS px times the pinch scale times device pixels, so text that
    only gets smaller CSS px while the scale grows doesn't count as zoomed."""
    return Js(mw.web, """(() => {
const a = [...document.querySelectorAll('a.deck')].find(a => a.innerText.includes(%s));
if (!a) return null;
const scale = (window.visualViewport ? visualViewport.scale : 1) * devicePixelRatio;
return [a.getBoundingClientRect().height * scale,
        document.documentElement.scrollWidth - window.innerWidth];
})()""" % json.dumps(DECK))


HEATMAP_LIKE_JS = """(() => {
const box = document.createElement('div');
box.id = 'kioku-test-chart';
box.innerHTML = '<div style="display:inline-block"><div><div style="float:right"><span id="kioku-test-chart-btn" style="padding:2px 8px">B</span></div><div style="clear:both"></div></div>'
  + '<svg width="636" height="109"><rect width="636" height="109" fill="#ccc"/></svg></div>';
document.body.appendChild(box);
window.__kioku_chart = () => {
  const svg = box.querySelector('svg').getBoundingClientRect();
  const btn = document.getElementById('kioku-test-chart-btn').getBoundingClientRect();
  return {svg: svg.right, button: btn.right, room: document.documentElement.clientWidth,
          scroll: document.documentElement.scrollWidth - window.innerWidth};
};
return true;
})()"""


def t_page_zoom():
    # TestFlight (iPad): View › Zoom In moved the page right, the text
    # stayed the same size (WKWebView pageZoom; kioku_platform.webview)
    mw.moveToState("deckBrowser")
    yield Until(lambda: mw.state == "deckBrowser", 10, "deck list")
    yield 1
    before = yield _deck_name_size()
    check(bool(before), "test deck not on the deck list")
    try:
        for _ in range(3):
            mw.form.actionZoomIn.trigger()
        yield 1.5
        zoomed = yield _deck_name_size()
        check(bool(zoomed), "test deck gone after Zoom In")
        ratio = zoomed[0] / before[0]
        check(ratio > 1.2, f"Zoom In x3 (130%) made the text {ratio:.2f}x as tall")
        check(zoomed[1] <= 1, f"zoomed page is {zoomed[1]} px wider than the window")
        # TestFlight (iPhone, 0.2.9 zoomed): Review Heatmap's chart and its
        # buttons ran off the right side. A chart like it: a 636px SVG in an
        # inline-block with a button floated right (kioku.webscripts fitCharts)
        chart = yield Js(mw.web, HEATMAP_LIKE_JS)
        yield 1
        chart = yield Js(mw.web, "window.__kioku_chart()")
        check(bool(chart), "chart not on the deck list")
        check(chart["svg"] <= chart["room"] + 1 and chart["button"] <= chart["room"] + 1,
              f"chart ends at {chart['svg']} px, its button at {chart['button']} px, window {chart['room']} px")
        check(chart["scroll"] <= 1, f"zoomed page with the chart is {chart['scroll']} px wider than the window")
    finally:
        mw.web.eval("document.getElementById('kioku-test-chart') && document.getElementById('kioku-test-chart').remove()")
        mw.form.actionResetZoom.trigger()
    yield 1.5
    reset = yield _deck_name_size()
    back = reset[0] / before[0]
    check(0.95 < back < 1.05, f"Reset Zoom left the text {back:.2f}x as tall")
    return f"130%: text {ratio:.2f}x, no sideways scroll, a wide chart fits; reset restores"


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


def t_main_window_keyboard():
    """Issue #4: on Android before 15 the keyboard's adjustResize resized
    the main window, which Qt keeps maximized, and Android showed its new
    surface above the Add window for a few frames (menu bar and black
    around the editor). The main window keeps the size it has without the
    keyboard, like the other windows (windows._fill_main)."""
    if sys.platform != "android":
        raise Skip(sys.platform)
    import aqt
    from aqt.qt import Qt
    from kioku import windows

    yield 0
    mw = aqt.mw
    states = mw.windowHandle().windowStates()
    check(not states & Qt.WindowState.WindowMaximized, f"main window maximized: {states}")
    avail = windows._available()
    geo = mw.geometry()
    check(geo.top() == avail.top() and geo.width() == avail.width() and geo.bottom() >= avail.bottom(),
          f"main window {geo.getRect()} doesn't cover {avail.getRect()}")
    return f"normal, {geo.width()}x{geo.height()}"


def t_main_keyboard_bar():
    """Android: the main window keeps its size while the keyboard is open
    (windows._fill_main), so on Android 11 to 14 the reviewer's bottom bar
    (Show Answer) stayed under the keyboard that its typing box opened.
    kioku.screenedges keeps the window out of the part the keyboard covers.
    A Qt line edit in the main window opens the keyboard here (a tap in the
    page does the same in use)."""
    if sys.platform != "android":
        raise Skip(sys.platform)
    import aqt
    from aqt.qt import QGuiApplication, QLineEdit

    mw = aqt.mw
    im = QGuiApplication.inputMethod()
    edit = QLineEdit(mw)
    edit.setGeometry(0, mw.height() // 4, mw.width(), 40)
    edit.show()
    try:
        edit.setFocus()
        yield 0.3
        im.show()
        yield Until(lambda: im.isVisible() and not im.keyboardRectangle().isEmpty(), 10,
                    "keyboard and its rectangle")
        yield 1
        ratio = mw.screen().devicePixelRatio()
        top = im.keyboardRectangle().top() / ratio
        bar = mw.bottomWeb
        bottom = bar.mapToGlobal(bar.rect().bottomLeft()).y()
        margin = mw.contentsMargins().bottom()
    finally:
        im.hide()
        edit.deleteLater()
    yield Until(lambda: not im.isVisible(), 10, "keyboard closed")
    yield 0.5
    check(bottom <= top + 1, f"bottom bar ends at y {bottom}, keyboard starts at {top:.0f}")
    after = mw.contentsMargins().bottom()
    check(after < margin, f"bottom margin {after} kept after the keyboard closed (was {margin})")
    return f"bar ends {bottom}, keyboard at {top:.0f}, margin {margin} -> {after}"


def t_keyboard_window_size():
    """Issue #4: on Android 11 to 14 the keyboard's adjustResize resized the
    app's window, and for a few frames Android showed the main window (drawn
    on its own surface below) in place of the Browse, Add or Edit window.
    KiokuActivity.onWindowAttributesChanged makes it adjustPan there: the
    window keeps its size (Qt's available geometry stays) and Qt still gets
    the keyboard's place (keyboardRectangle, which adjustNothing lost)."""
    if sys.platform != "android":
        raise Skip(sys.platform)
    import platform

    level = platform.android_ver().api_level
    if not 30 <= level <= 34:
        raise Skip(f"Android API {level}")
    from aqt.qt import QGuiApplication, QRect

    im = QGuiApplication.inputMethod()
    screen = QGuiApplication.primaryScreen()
    before = screen.availableGeometry()
    heights = [before.height()]

    def changed(rect: QRect) -> None:
        heights.append(rect.height())

    screen.availableGeometryChanged.connect(changed)
    browser = aqt.dialogs.open("Browser", mw)
    try:
        yield Until(lambda: windows_of("Browser"), 15, "Browse window")
        browser.form.searchEdit.lineEdit().setFocus()
        yield 0.3
        im.show()
        yield Until(lambda: im.isVisible() and not im.keyboardRectangle().isEmpty(), 10,
                    "keyboard and its rectangle")
        yield 1
        kbd = im.keyboardRectangle()
    finally:
        im.hide()
        screen.availableGeometryChanged.disconnect(changed)
        close_window(browser)
    yield Until(lambda: not im.isVisible(), 10, "keyboard closed")
    check(min(heights) == before.height(),
          f"available height {before.height()} went down to {min(heights)} with the keyboard")
    return f"window kept {before.width()}x{before.height()}, keyboard at y {kbd.y():.0f}"


def t_symbol_glyphs():
    """Symbols in Anki's Qt windows come from a font that has them. On
    Android, Qt falls back only to the fonts QT_ANDROID_FONTS names, and the
    system's Noto Sans Symbols file it kept for the family was the small
    one: the Add window showed "History" with a box for Anki's down arrow
    (kioku_platform._symbol_fonts, install_fonts)."""
    from PyQt6.QtGui import QTextLayout
    from aqt.utils import downArrow

    yield 0
    missing = []
    for char in downArrow() + "\u25bc\u25b6\u2605\u2713":
        layout = QTextLayout(char, QApplication.font())
        layout.beginLayout()
        layout.createLine()
        layout.endLayout()
        runs = layout.glyphRuns()
        if not any(run.rawFont().supportsCharacter(ord(char)) for run in runs):
            missing.append(f"U+{ord(char):04X}")
    check(not missing, f"no font has {missing}")
    return "all drawn"


def t_accessibility():
    """Issue #22: with an accessibility service on that is not a screen
    reader (password managers, Xiaomi's and Samsung's system services), Qt's
    accessibility bridge made each of the service's queries wait for the Qt
    main thread and the app lagged. Kioku keeps the bridge only for screen
    readers (KiokuActivity.screenReaderOn). Meaningful with a service on:
    apptest on the emulator with Accessibility Menu or TalkBack."""
    if sys.platform != "android":
        raise Skip(sys.platform)
    from kioku_platform import bridge

    # Qt's QtAccessibilityDelegate reads it when a service turns on (this
    # PyQt6 has no QAccessible to ask Qt directly)
    state = bridge.call("accessibility")
    yield 0
    disabled = os.environ.get("QT_ANDROID_DISABLE_ACCESSIBILITY") == "1"
    if state["screenReader"]:
        check(not disabled, f"screen reader on but Qt accessibility off: {state}")
        return "screen reader: Qt accessibility on"
    check(disabled, f"no screen reader but Qt accessibility allowed: {state}")
    return "service, no screen reader: Qt accessibility off" if state["enabled"] else "no service"


def t_ankiweb_service():
    """A sync that ends at once stopped KiokuAnkiWebService before Android's
    UI thread had run its startForeground(); Android 11 and older then
    closed the app ("Context.startForegroundService() did not then call
    Service.startForeground()", a Realme 5 Pro after logging in). Starts it
    twice (sync, then a title change) and stops it in the same breath: the
    app has to survive and the service has to be gone afterwards. Only
    Android 11 and older crashed without the fix (M30s, API 30 emulator)."""
    if sys.platform != "android":
        raise Skip(sys.platform)
    from kioku import ankiwebsync
    from kioku_platform import bridge

    # a logged-in profile syncs at start
    yield Until(lambda: not ankiwebsync._service_running, 120, "sync at start to end")
    # posted to Android's UI thread, run back to back as after a blocked one
    bridge.call("ankiWebService", running=True, title="")
    bridge.call("ankiWebService", running=True, title="Kioku test")
    bridge.call("ankiWebService", running=False, title="")
    # the state is read on this thread at once, maybe before the posted calls
    # ran: give them, and a crash without the fix (within about a second),
    # 3 s first
    begun = time.monotonic()
    stopped = {"running": False, "pending": False}
    yield Until(lambda: time.monotonic() - begun > 3
                and bridge.call("ankiWebService.state") == stopped, 15, "service stopped")
    import platform

    api = platform.android_ver().api_level
    return f"start, start, stop at once: app alive, service stopped (API {api})"


def t_microphone():
    """Issue #19: an add-on recording through AVAudioRecorder (rubicon-objc)
    needs NSMicrophoneUsageDescription, else iOS ends the app. Records a
    second the way such an add-on does when the permission is granted
    (apptest.py grants it on the Simulator); never asks for it."""
    if sys.platform != "ios":
        raise Skip(sys.platform)
    from rubicon.objc import NSDictionary, ObjCClass, at
    from rubicon.objc.runtime import load_library

    from kioku_platform.audio import _activate_session
    from kioku_platform.webview import prop

    load_library("AVFoundation")
    bundle = prop(ObjCClass("NSBundle"), "mainBundle")
    text = bundle.objectForInfoDictionaryKey_(at("NSMicrophoneUsageDescription"))
    check(text is not None and str(text).strip() != "",
          "Info.plist has no NSMicrophoneUsageDescription")
    session = prop(ObjCClass("AVAudioSession"), "sharedInstance")
    permission = int(prop(session, "recordPermission"))
    names = {0x67726E74: "granted", 0x64656E79: "denied", 0x756E6474: "not asked yet"}
    if permission != 0x67726E74:
        return f"usage description set; not recorded (permission {names.get(permission, permission)})"
    path = os.path.join(WORK, "mic.wav")
    if os.path.exists(path):
        os.unlink(path)
    url = ObjCClass("NSURL").fileURLWithPath_(at(path))
    settings = NSDictionary.dictionaryWithDictionary_({
        "AVFormatIDKey": 0x6C70636D,  # kAudioFormatLinearPCM
        "AVSampleRateKey": 44100.0,
        "AVNumberOfChannelsKey": 1,
    })
    try:
        check(bool(session.setCategory_error_(at("AVAudioSessionCategoryPlayAndRecord"), None)),
              "setCategory PlayAndRecord failed")
        session.setActive_error_(True, None)
        recorder = ObjCClass("AVAudioRecorder").alloc().initWithURL_settings_error_(url, settings, None)
        check(recorder is not None, "AVAudioRecorder could not be created")
        check(bool(recorder.record()), "AVAudioRecorder.record() returned NO")
        yield 1.0
        seconds = float(prop(recorder, "currentTime"))
        recorder.stop()
        yield 0.3
    finally:
        _activate_session()  # card audio plays as before
    size = os.path.getsize(path) if os.path.exists(path) else 0
    if size:
        os.unlink(path)
    check(size > 4096, f"recording has {size} bytes")
    return f"recorded {seconds:.1f} s, {size} bytes"


def safe_css(web: AnkiWebView, want: str):
    """The page's --kioku-safe-* properties, once they are want (or 5 s)."""
    css = None
    for _ in range(20):
        css = yield Js(web, "(() => { const s = getComputedStyle(document.documentElement);"
                            " return ['top','right','bottom','left'].map("
                            "x => s.getPropertyValue('--kioku-safe-' + x).trim()).join(' '); })()")
        if css == want:
            break
        yield 0.25
    return css


def t_addon_window():
    """Issues #32, #33: an add-on window that asks for it has no title bar
    and reaches the screen's edges, its page padded by --kioku-safe-*; it
    fills the screen before it is first drawn; add-ons can hide Anki's
    menu row."""
    from aqt.qt import QDialog, QMargins, QVBoxLayout
    from kioku import windows

    w = QDialog(mw)
    w.setWindowTitle("Kioku add-on window test")
    QVBoxLayout(w).setContentsMargins(0, 0, 0, 0)
    web = AnkiWebView(parent=w)
    w.layout().addWidget(web)
    web.stdHtml("<p id=kt>add-on page</p>")
    w.setProperty("kioku_hide_titlebar", True)
    w.setProperty("kioku_edge_to_edge", True)
    w.resize(300, 200)
    w.show()
    try:
        avail = windows._available()
        size = w.size()
        check(size.width() >= avail.width() and size.height() >= avail.height(),
              f"{size.width()}x{size.height()} when shown, screen {avail.width()}x{avail.height()}")
        yield 0.5
        check(windows.WindowManager._bar(w) is None, "title bar added")
        m = w.contentsMargins()
        # Android: the window is a pixel taller than the screen (windows._fill)
        check((m.left(), m.top(), m.right(), m.bottom()) == (0, 0, 0, windows._overhang(w)),
              f"margins {(m.left(), m.top(), m.right(), m.bottom())}")
        safe = QMargins(w.windowHandle().safeAreaMargins())
        # Android: minus the window's pixel below the screen, whose margin is set
        safe.setBottom(max(0, safe.bottom() - windows._overhang(w)))
        area = windows.safe_area(w)
        check(area == safe, f"safe_area {(area.left(), area.top(), area.right(), area.bottom())}"
              f" != {(safe.left(), safe.top(), safe.right(), safe.bottom())}")
        want = " ".join(f"{v}px" for v in (safe.top(), safe.right(), safe.bottom(), safe.left()))
        css = yield from safe_css(web, want)
        check(css == want, f"page has {css!r}, safe area {want}")
        # given back the title bar, the window keeps out of the status bar
        w.setProperty("kioku_hide_titlebar", False)
        w.setProperty("kioku_edge_to_edge", False)
        yield 0.3
        m = w.contentsMargins()
        check(m.top() == safe.top() + windows.BAR_HEIGHT and windows.safe_area(w) == QMargins(),
              f"with title bar: top margin {m.top()}")
        css = yield from safe_css(web, "0px 0px 0px 0px")
        check(css == "0px 0px 0px 0px", f"page kept {css!r} after edge to edge was turned off")
        # the menu row
        bar = mw.form.menubar
        mw.setProperty("kioku_hide_menu_row", True)
        check(bar.maximumHeight() == 0, "menu row still shown")
        mw.setProperty("kioku_hide_menu_row", None)
        check(bar.maximumHeight() > 0 or mw.fullscreen or not mw.pm.meta.get("kioku_menu_row", True),
              "menu row not given back")
    finally:
        mw.setProperty("kioku_hide_menu_row", None)
        w.close()
    return f"safe area {want}"


def t_safe_mode_request():
    """Issue #32: the app icon's "Start in Safe Mode" while Kioku runs
    leaves a request (iOS: the scene delegate's shortcut method, added in
    main.mm) and Kioku offers to close; Cancel drops the request."""
    from aqt.qt import QMessageBox
    from kioku import safemode

    request = os.path.join(kioku_platform.documents_dir(), safemode.REQUEST)
    check(not os.path.exists(request), "a request was left from before")
    how = "request file"
    if sys.platform == "ios":
        from rubicon.objc import ObjCClass
        from kioku_platform.webview import prop

        app = prop(ObjCClass("UIApplication"), "sharedApplication")
        scene = prop(app, "connectedScenes").anyObject()
        item = ObjCClass("UIApplicationShortcutItem").alloc().initWithType_localizedTitle_(
            "io.ankidesk.kioku.safe-mode", "Start in Safe Mode")
        prop(scene, "delegate").windowScene_performActionForShortcutItem_completionHandler_(scene, item, None)
        how = "scene delegate's shortcut method"
    else:
        open(request, "w").close()
    try:
        check(os.path.exists(request), f"no request from the {how}")
        safemode._request_while_running()
        boxes = lambda: [w for w in QApplication.topLevelWidgets()  # noqa: E731
                         if isinstance(w, QMessageBox) and w.isVisible() and "safe mode" in w.text()]
        yield Until(lambda: boxes(), 10, "the offer to close Kioku")
        box = boxes()[0]
        labels = [b.text() for b in box.buttons()]
        check("Close Kioku" in labels, f"buttons {labels}")
        box.button(QMessageBox.StandardButton.Cancel).click()
        yield Until(lambda: not os.path.exists(request), 5, "request dropped on Cancel")
    finally:
        if os.path.exists(request):
            os.remove(request)
    return f"{how}, offer to close, Cancel dropped it"


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
    ("editor-formatting", t_editor_formatting),
    ("editor-caret", t_editor_caret),
    ("deck-list", t_deck_browser),
    ("page-zoom", t_page_zoom),
    ("bottom-buttons", t_bottom_buttons),
    ("browse", t_browse),
    ("browse-columns", t_browse_columns),
    ("numpad-done", t_numpad_done),
    ("study", t_study),
    ("review", t_review),
    ("undo", t_undo),
    ("review-focus", t_review_focus),
    ("card-keys", t_card_keys),
    ("review-keys", t_review_keys),
    ("gamepad", t_gamepad),
    ("gamepad-native", t_gamepad_native),
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
    ("microphone", t_microphone),
    ("main-window-keyboard", t_main_window_keyboard),
    ("main-keyboard-bar", t_main_keyboard_bar),
    ("keyboard-window-size", t_keyboard_window_size),
    ("symbol-glyphs", t_symbol_glyphs),
    ("accessibility", t_accessibility),
    ("ankiweb-service", t_ankiweb_service),
    ("addon-window", t_addon_window),
    ("safe-mode-request", t_safe_mode_request),
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
        self.deadline = self.started + getattr(fn, "timeout", STEP_TIMEOUT)
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
            self.finish("fail", f"took longer than {self.deadline - self.started:.0f} s")
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
