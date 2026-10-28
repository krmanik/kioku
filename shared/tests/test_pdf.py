"""The QtPdf stand-in (kioku.pdf) as the Incremento add-on uses it, over a fake
platform PDF backend."""

from __future__ import annotations

import os
import sys
import threading
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


class PdfError(Exception):
    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class FakeBackend(types.ModuleType):
    """Two A5 pages; any file whose name has "bad"/"locked" fails to open."""

    PdfError = PdfError

    def __init__(self) -> None:
        super().__init__("kioku_platform.pdf")
        self.opened: list[str] = []
        self.closed = 0

    def open(self, path: str, password: str) -> str:
        if not os.path.exists(path):
            raise PdfError("missing")
        if "bad" in path:
            raise PdfError("format")
        if "locked" in path and password != "pw":
            raise PdfError("password")
        self.opened.append(path)
        return path

    def close(self, doc: str) -> None:
        self.closed += 1

    def page_sizes(self, doc: str) -> list[tuple[float, float]]:
        return [(420.0, 595.0), (595.0, 420.0)]

    def metadata(self, doc: str) -> dict:
        return {"Title": "Notes", "CreationDate": 1_700_000_000}

    def text(self, doc: str, page: int) -> str:
        return f"text of page {page + 1}"

    def render(self, doc: str, page: int, width: int, height: int) -> bytes:
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(data)


backend = FakeBackend()
sys.modules["kioku_platform.pdf"] = backend
sys.modules["kioku_platform"].pdf = backend  # type: ignore[attr-defined]

from PyQt6.QtPdf import QPdfDocument  # noqa: E402  (shared/python's stand-in)

from kioku.pdf import QPdfDocument as KiokuDocument  # noqa: E402


def pdf(tmp_path, name: str = "a.pdf") -> str:
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.4")
    return str(path)


def test_desktop_pyqt_or_stand_in() -> None:
    # host tests run with desktop PyQt6, which has QtPdf; the apps get ours
    assert QPdfDocument.__module__ in ("PyQt6.QtPdf", "kioku.pdf")


def test_load_and_read(platform, tmp_path) -> None:
    doc = KiokuDocument(None)
    statuses: list[str] = []
    doc.statusChanged.connect(lambda s: statuses.append(s.name))
    assert doc.load(pdf(tmp_path)) == KiokuDocument.Error.None_
    assert statuses == ["Loading", "Ready"] and doc.status() == KiokuDocument.Status.Ready
    assert doc.pageCount() == 2
    assert doc.pagePointSize(1).width() == 595.0
    assert not doc.pagePointSize(2).isValid()
    assert doc.metaData(KiokuDocument.MetaDataField.Title) == "Notes"
    assert doc.metaData(KiokuDocument.MetaDataField.Author) == ""
    assert doc.metaData(KiokuDocument.MetaDataField.CreationDate).toSecsSinceEpoch() == 1_700_000_000
    selection = doc.getAllText(1)
    assert selection.isValid() and selection.text() == "text of page 2"
    assert not doc.getAllText(5).isValid()
    image = doc.render(0, QSize(100, 141))
    assert (image.width(), image.height()) == (100, 141)
    assert doc.render(9, QSize(100, 141)).isNull()
    doc.close()
    assert doc.status() == KiokuDocument.Status.Null and doc.pageCount() == 0
    assert backend.closed >= 1


def test_errors(platform, tmp_path) -> None:
    doc = KiokuDocument(None)
    assert doc.load(str(tmp_path / "none.pdf")) == KiokuDocument.Error.FileNotFound
    assert doc.status() == KiokuDocument.Status.Error and doc.pageCount() == 0
    assert doc.load(pdf(tmp_path, "bad.pdf")) == KiokuDocument.Error.InvalidFileFormat
    locked = pdf(tmp_path, "locked.pdf")
    assert doc.load(locked) == KiokuDocument.Error.IncorrectPassword
    doc.setPassword("pw")
    assert doc.load(locked) == KiokuDocument.Error.None_


def test_from_a_worker_thread(platform, tmp_path) -> None:
    # Incremento counts pages and renders covers in worker threads
    path = pdf(tmp_path)
    out: list = []

    def work() -> None:
        doc = KiokuDocument(None)
        doc.load(path)
        out.append((doc.pageCount(), doc.render(0, QSize(10, 14)).isNull()))
        doc.close()

    thread = threading.Thread(target=work)
    thread.start()
    thread.join()
    assert out == [(2, False)]
