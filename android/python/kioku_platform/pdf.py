"""PDF documents for kioku.pdf (PyQt6.QtPdf) through PdfRenderer
(KiokuBridge.java). PdfRenderer reads text only from Android 15 on and no
metadata at all, so the document info is read here when it isn't compressed."""

from __future__ import annotations

import builtins
import os
import re
import tempfile
import threading
from typing import Any

from . import bridge

# QPdfDocument.MetaDataField names → document info keys
FIELDS = {
    "Title": b"Title",
    "Subject": b"Subject",
    "Author": b"Author",
    "Keywords": b"Keywords",
    "Producer": b"Producer",
    "Creator": b"Creator",
    "CreationDate": b"CreationDate",
    "ModificationDate": b"ModDate",
}


class PdfError(Exception):
    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class Document:
    def __init__(self, path: str, id: int, sizes: list[tuple[float, float]]) -> None:
        self.path = path
        self.id = id
        self.sizes = sizes


def open(path: str, password: str) -> Document:
    # PdfRenderer takes passwords only from Android 15 on (LoadParams)
    result = bridge.call("pdf.open", path=path)
    if "fail" in result:
        raise PdfError(result["fail"])
    return Document(path, result["id"], [tuple(s) for s in result["sizes"]])


def close(doc: Document) -> None:
    bridge.call("pdf.close", id=doc.id)


def page_sizes(doc: Document) -> list[tuple[float, float]]:
    return doc.sizes


def text(doc: Document, page: int) -> str:
    return bridge.call("pdf.text", id=doc.id, page=page)


def render(doc: Document, page: int, width: int, height: int) -> bytes:
    out = os.path.join(tempfile.gettempdir(), f"kioku-pdf-{threading.get_ident()}.png")
    try:
        bridge.call("pdf.render", id=doc.id, page=page, width=width, height=height, out=out)
        with builtins.open(out, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(out):
            os.remove(out)


def metadata(doc: Document) -> dict[str, Any]:
    try:
        return _info(doc.path)
    except Exception:
        return {}


def _info(path: str) -> dict[str, Any]:
    """The trailer's /Info dictionary, when it is a plain object."""
    with builtins.open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - 65536))
        tail = f.read()
        refs = re.findall(rb"/Info\s+(\d+)\s+(\d+)\s+R", tail)
        if not refs:
            return {}
        num, gen = refs[-1]
        f.seek(0)
        data = f.read()
    match = re.search(rb"(?<!\d)" + num + rb"\s+" + gen + rb"\s+obj\s*<<(.*?)>>\s*endobj", data, re.S)
    if match is None:
        return {}
    body = match.group(1)
    meta: dict[str, Any] = {}
    for field, key in FIELDS.items():
        m = re.search(rb"/" + key + rb"\s*(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>)", body, re.S)
        if m is None:
            continue
        value = _string(m.group(1))
        meta[field] = _date(value) if field.endswith("Date") else value
    return meta


def _string(token: bytes) -> str:
    if token.startswith(b"<"):
        raw = bytes.fromhex(re.sub(rb"\s", b"", token[1:-1]).decode())
    else:
        escapes = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}

        def unescape(m: re.Match) -> bytes:
            c = m.group(1)
            if c[:1].isdigit():
                return bytes([int(c, 8) & 0xFF])
            return escapes.get(c, c)

        raw = re.sub(rb"\\([0-7]{1,3}|.)", unescape, token[1:-1], flags=re.S)
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", "replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace")
    return raw.decode("latin-1")


def _date(value: str) -> float | None:
    """D:YYYYMMDDHHmmSS+HH'mm' → seconds since the epoch."""
    import calendar

    m = re.match(r"(?:D:)?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz+-])?(\d{2})?'?(\d{2})?", value)
    if m is None:
        return None
    year, month, day, hour, minute, second = (int(g or d) for g, d in zip(m.groups()[:6], (0, 1, 1, 0, 0, 0)))
    seconds = calendar.timegm((year, month, day, hour, minute, second))
    sign, tzh, tzm = m.group(7), m.group(8), m.group(9)
    if sign in ("+", "-"):
        offset = int(tzh or 0) * 3600 + int(tzm or 0) * 60
        seconds -= offset if sign == "+" else -offset
    return seconds
