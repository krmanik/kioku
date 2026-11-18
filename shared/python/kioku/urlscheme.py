"""kioku:// links: other apps (Shortcuts, dictionaries) add notes, sync and
search, with AnkiMobile's actions and parameters
(https://docs.ankiweb.net/ankimobile/url-schemes) under Kioku's own scheme:

  kioku://x-callback-url/addnote?type=Basic&deck=Default&fldFront=...&fldBack=...
      optional: profile=, tags= (space separated), dupes=1, x-success=<url>
  kioku://x-callback-url/sync
  kioku://x-callback-url/search?query=...

addnote adds the note at once (the add screen's editor can't be filled in
from Python), then opens x-success if there is one. A field that is only a
link to an image or audio file is downloaded into the collection's media,
as AnkiMobile does. Type and deck default to what the add screen would pick.

iOS (Info.plist CFBundleURLTypes) and Android (an ACTION_VIEW intent filter)
hand the link to Qt, which passes it to QDesktopServices; install() takes
the scheme there before the event loop runs, so a link that starts the app
is not missed. Links that come before a profile is open wait for it.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit

logger = logging.getLogger("kioku.urlscheme")

SCHEME = "kioku"
ACTIONS = ("addnote", "sync", "search")
# The add screen's lists (aqt.editor_legacy pics/audio)
IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "svg", "webp", "ico", "avif"}
SOUND_EXTS = {
    "3gp", "aac", "avi", "flac", "flv", "m4a", "mkv", "mov", "mp3", "mp4",
    "mpeg", "mpg", "oga", "ogg", "ogv", "ogx", "opus", "spx", "swf", "wav",
    "webm",
}  # fmt: skip
MAX_DOWNLOAD = 50 * 1024 * 1024


class LinkError(Exception):
    """A link Kioku can't follow; the message is shown to the user."""


@dataclass
class Link:
    action: str
    params: dict[str, str] = field(default_factory=dict)


def parse(url: str) -> Link:
    """kioku://x-callback-url/<action>?k=v&... (kioku://<action> also works).
    Values are percent-decoded only: a "+" stays a "+", as in iOS's URLs."""
    parts = urlsplit(url)
    if parts.scheme.lower() != SCHEME:
        raise LinkError(f"Not a {SCHEME}:// link: {url}")
    host = parts.netloc.lower()
    path = parts.path.strip("/")
    action = path if host == "x-callback-url" else "/".join(p for p in (host, path) if p)
    params: dict[str, str] = {}
    for pair in parts.query.split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        params[unquote(key)] = unquote(value)
    return Link(action.lower(), params)


def media_link(value: str) -> tuple[str, str] | None:
    """(url, extension) when a field holds only a link to an image or sound."""
    value = value.strip()
    if not re.fullmatch(r"https?://\S+", value, re.IGNORECASE):
        return None
    ext = value.rsplit(".", 1)[-1].lower()
    if ext in IMAGE_EXTS or ext in SOUND_EXTS:
        return value, ext
    return None


def media_name(url: str) -> str:
    """The file name a download is saved as: the link's last path part, or
    the last query value for dynamic links (getImage?id=1&fakePath=foo.jpg)."""
    name = re.split(r"[/=&?]", url)[-1]
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", unquote(name)).strip(". ")
    return name or "download"


def media_html(name: str, ext: str) -> str:
    if ext in IMAGE_EXTS:
        return f'<img src="{html.escape(name, quote=True)}">'
    return f"[sound:{name}]"


@dataclass
class NewNote:
    note: Any  # anki.notes.Note
    deck_id: int
    downloads: dict[str, tuple[str, str]]  # field name -> (url, ext)
    x_success: str | None


def build_note(col: Any, params: dict[str, str], profile: str | None = None) -> NewNote:
    """Check an addnote link against the collection and make its note
    (not added yet; media links are left for fill_media)."""
    from anki.notes import NoteFieldsCheckResult

    wanted_profile = params.get("profile")
    if wanted_profile and profile is not None and wanted_profile != profile:
        raise LinkError(
            f'The link is for the profile "{wanted_profile}", but "{profile}" is open.'
        )
    defaults = col.defaults_for_adding(current_review_card=None)
    if name := params.get("type"):
        notetype = col.models.by_name(name)
        if notetype is None:
            raise LinkError(f'There is no note type "{name}".')
    else:
        notetype = col.models.get(defaults.notetype_id)
    if deck := params.get("deck"):
        deck_id = col.decks.id_for_name(deck)
        if deck_id is None:
            raise LinkError(f'There is no deck "{deck}".')
    else:
        deck_id = col.default_deck_for_notetype(notetype["id"]) or defaults.deck_id

    note = col.new_note(notetype)
    names = note.keys()
    downloads: dict[str, tuple[str, str]] = {}
    for key, value in params.items():
        if not key.startswith("fld"):
            continue
        fname = key[3:]
        if fname not in names:
            raise LinkError(
                f'The note type "{notetype["name"]}" has no field "{fname}" '
                f"(its fields: {', '.join(names)})."
            )
        if link := media_link(value):
            downloads[fname] = link
            # a placeholder, so the empty and duplicate checks see something
            note[fname] = media_html(media_name(link[0]), link[1])
        else:
            note[fname] = value
    note.tags = col.tags.split(params.get("tags", ""))

    state = note.fields_check()
    if state == NoteFieldsCheckResult.EMPTY:
        raise LinkError(f'The link leaves the first field ("{names[0]}") empty.')
    if state == NoteFieldsCheckResult.DUPLICATE and params.get("dupes") != "1":
        raise LinkError(
            f'A note with this "{names[0]}" already exists (add dupes=1 to the link to add it anyway).'
        )
    return NewNote(note, deck_id, downloads, x_success(params))


def x_success(params: dict[str, str]) -> str | None:
    url = params.get("x-success")
    if not url:
        return None
    scheme = urlsplit(url).scheme.lower()
    if not scheme or scheme in (SCHEME, "file"):
        raise LinkError(f"x-success can't be a {scheme or 'relative'} link: {url}")
    return url


def download(url: str) -> bytes:
    from anki.httpclient import HttpClient

    with HttpClient() as client:
        client.timeout = 30
        resp = client.get(url)
        resp.raise_for_status()
        data = bytearray()
        for chunk in resp.iter_content(chunk_size=1 << 16):
            data += chunk
            if len(data) > MAX_DOWNLOAD:
                raise LinkError(f"{url} is larger than {MAX_DOWNLOAD >> 20} MB.")
        return bytes(data)


def fill_media(col: Any, new: NewNote, data: dict[str, bytes]) -> None:
    """Save the downloads into the media folder and link them in their fields."""
    for fname, (url, ext) in new.downloads.items():
        saved = col.media.write_data(media_name(url), data[fname])
        new.note[fname] = media_html(saved, ext)


# Qt side ----------------------------------------------------------------------

_receiver: Any = None
_pending: list[str] = []


def install() -> None:
    """Take kioku:// links from QDesktopServices. Call before aqt.run()."""
    global _receiver
    from aqt import gui_hooks
    from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal, pyqtSlot
    from PyQt6.QtGui import QDesktopServices

    class _Receiver(QObject):
        received = pyqtSignal(str)

        @pyqtSlot(QUrl)
        def handle(self, url: QUrl) -> None:
            # Queued, so the link is handled on the main thread after
            # QDesktopServices::openUrl returns: Android calls this on its
            # UI thread (onNewIntent), and opening Browse from inside
            # openUrl crashed the app (iOS Simulator)
            self.received.emit(url.toString(QUrl.ComponentFormattingOption.FullyEncoded))

    _receiver = _Receiver()
    _receiver.received.connect(_handle_safely, Qt.ConnectionType.QueuedConnection)
    QDesktopServices.setUrlHandler(SCHEME, _receiver, "handle")
    gui_hooks.profile_did_open.append(_after_profile_open)


def _handle_safely(url: str) -> None:
    try:
        handle(url)
    except Exception as err:
        logger.exception("handling %s", url)
        if (mw := _ready()) is not None:
            _warn(mw, f"Kioku couldn't follow the link: {err}")


def _ready() -> Any:
    import aqt

    mw = aqt.mw
    if mw is None or mw.col is None:
        return None
    return mw


def _after_profile_open() -> None:
    import aqt

    if _pending and aqt.mw is not None:
        # let the main screen come up first
        aqt.mw.progress.single_shot(500, _run_pending, requires_collection=True)


def _run_pending() -> None:
    while _pending and _ready() is not None:
        handle(_pending.pop(0))


def handle(url: str) -> None:
    logger.info("link %s", url)
    mw = _ready()
    if mw is None:
        _pending.append(url)
        return
    try:
        link = parse(url)
        if link.action == "addnote":
            _add_note(mw, link)
        elif link.action == "sync":
            mw.on_sync_button_clicked()
        elif link.action == "search":
            import aqt

            aqt.dialogs.open("Browser", mw, search=(link.params.get("query", ""),))
        elif link.action:
            raise LinkError(
                f'Kioku can\'t "{link.action}" from a link. It can: {", ".join(ACTIONS)}.'
            )
    except LinkError as err:
        _warn(mw, str(err))


def _warn(mw: Any, text: str) -> None:
    from aqt.utils import showWarning

    showWarning(text, parent=mw, title="Kioku link")


def _add_note(mw: Any, link: Link) -> None:
    new = build_note(mw.col, link.params, mw.pm.name)
    if not new.downloads:
        _save(mw, new, {})
        return

    def fetch() -> dict[str, bytes]:
        return {fname: download(url) for fname, (url, _) in new.downloads.items()}

    def done(future: Any) -> None:
        try:
            data = future.result()
        except LinkError as err:
            _warn(mw, str(err))
            return
        except Exception as err:
            _warn(mw, f"Couldn't download a file for the note: {err}")
            return
        _save(mw, new, data)

    mw.taskman.with_progress(fetch, done, label="Downloading…", uses_collection=False)


def _save(mw: Any, new: NewNote, data: dict[str, bytes]) -> None:
    from aqt.operations.note import add_note
    from aqt.utils import tooltip

    fill_media(mw.col, new, data)

    def added(_: Any) -> None:
        deck = mw.col.decks.name(new.deck_id)
        tooltip(f"Added to {deck}", parent=mw)
        if new.x_success:
            _open(new.x_success)

    add_note(parent=mw, note=new.note, target_deck_id=new.deck_id).success(
        added
    ).run_in_background()


def _open(url: str) -> None:
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices

    QDesktopServices.openUrl(QUrl(url))
