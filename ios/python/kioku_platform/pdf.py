"""PDF documents for kioku.pdf (PyQt6.QtPdf) through PDFKit."""

from __future__ import annotations

import ctypes
import os
from typing import Any

from rubicon.objc import Block, CGRect, CGSize, ObjCClass, at
from rubicon.objc.runtime import load_library, objc_id

from .webview import prop

load_library("PDFKit")

PDFDocument = ObjCClass("PDFDocument")
NSURL = ObjCClass("NSURL")
UIBezierPath = ObjCClass("UIBezierPath")
UIColor = ObjCClass("UIColor")
UIGraphicsImageRenderer = ObjCClass("UIGraphicsImageRenderer")
UIGraphicsImageRendererFormat = ObjCClass("UIGraphicsImageRendererFormat")

MEDIA_BOX = 0  # kPDFDisplayBoxMediaBox

# QPdfDocument.MetaDataField names → PDFDocument attribute keys
FIELDS = {
    "Title": "Title",
    "Subject": "Subject",
    "Author": "Author",
    "Keywords": "Keywords",
    "Producer": "Producer",
    "Creator": "Creator",
    "CreationDate": "CreationDate",
    "ModificationDate": "ModDate",
}


class PdfError(Exception):
    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


def open(path: str, password: str) -> Any:
    if not os.path.isfile(path):
        raise PdfError("missing")
    doc = PDFDocument.alloc().initWithURL_(NSURL.fileURLWithPath_(at(path)))
    if doc is None:
        raise PdfError("format")
    if prop(doc, "isLocked") and not doc.unlockWithPassword_(at(password)):
        raise PdfError("password")
    return doc


def close(doc: Any) -> None:
    pass


def page_sizes(doc: Any) -> list[tuple[float, float]]:
    sizes = []
    for i in range(prop(doc, "pageCount")):
        page = doc.pageAtIndex_(i)
        rect = page.boundsForBox_(MEDIA_BOX)
        w, h = rect.size.width, rect.size.height
        if prop(page, "rotation") % 180:
            w, h = h, w
        sizes.append((w, h))
    return sizes


def metadata(doc: Any) -> dict[str, Any]:
    attrs = prop(doc, "documentAttributes")
    meta: dict[str, Any] = {}
    if attrs is None:
        return meta
    for field, key in FIELDS.items():
        value = attrs.objectForKey_(at(key))
        if value is None:
            continue
        if value.isKindOfClass_(ObjCClass("NSDate")):
            meta[field] = value.timeIntervalSince1970()
        elif value.isKindOfClass_(ObjCClass("NSArray")):
            meta[field] = ", ".join(str(v) for v in value)
        else:
            meta[field] = str(value)
    return meta


def text(doc: Any, page: int) -> str:
    value = prop(doc.pageAtIndex_(page), "string")
    return str(value) if value is not None else ""


def render(doc: Any, page: int, width: int, height: int) -> bytes:
    """PNG of the page stretched to width x height, like QPdfDocument.render."""
    thumb = doc.pageAtIndex_(page).thumbnailOfSize_forBox_(CGSize(width, height), MEDIA_BOX)
    fmt = UIGraphicsImageRendererFormat.alloc().init()
    fmt.setScale_(1.0)
    renderer = UIGraphicsImageRenderer.alloc().initWithSize_format_(CGSize(width, height), fmt)
    rect = CGRect((0, 0), (width, height))

    def draw(context):  # type: ignore[no-untyped-def]
        prop(UIColor, "whiteColor").setFill()
        UIBezierPath.bezierPathWithRect_(rect).fill()
        thumb.drawInRect_(rect)

    data = renderer.PNGDataWithActions_(Block(draw, None, objc_id))
    pointer = prop(data, "bytes")
    pointer = getattr(pointer, "value", pointer)
    return ctypes.string_at(pointer, prop(data, "length"))
