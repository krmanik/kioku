"""PyQt6.QtPdf on the platform's PDF renderer (kioku_platform.pdf: PDFKit on
iOS, PdfRenderer on Android). Qt's own QtPdf is built from Chromium's PDFium
and isn't available for iOS or Android, but add-ons import it (Incremento
reads page counts, titles and text, and renders covers). This covers
QPdfDocument and QPdfSelection; the models and widgets are left out."""

from __future__ import annotations

import enum
import threading
from typing import Any

from PyQt6.QtCore import QDateTime, QIODevice, QObject, QPointF, QRectF, QSize, QSizeF, pyqtSignal
from PyQt6.QtGui import QImage

import kioku_platform.pdf as backend


class QPdfSelection:
    def __init__(self, text: str = "", start: int = -1) -> None:
        self._text = text
        self._start = start

    def isValid(self) -> bool:
        return self._start >= 0

    def text(self) -> str:
        return self._text

    def bounds(self) -> list:
        return []

    def boundingRectangle(self) -> QRectF:
        return QRectF()

    def startIndex(self) -> int:
        return self._start

    def endIndex(self) -> int:
        return self._start + len(self._text) if self._start >= 0 else -1

    def copyToClipboard(self, mode: Any = None) -> None:
        from PyQt6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(self._text)


class QPdfDocumentRenderOptions:
    class Rotation(enum.Enum):
        None_ = 0
        Clockwise90 = 1
        Clockwise180 = 2
        Clockwise270 = 3

    class RenderFlag(enum.Flag):
        None_ = 0
        Annotations = 1
        OptimizedForLcd = 2
        Grayscale = 4
        ForceHalftone = 8
        TextAliased = 16
        ImageAliased = 32
        PathAliased = 64

    def __init__(self) -> None:
        self._rotation = QPdfDocumentRenderOptions.Rotation.None_
        self._flags = QPdfDocumentRenderOptions.RenderFlag.None_
        self._clip = QRectF()

    def rotation(self) -> QPdfDocumentRenderOptions.Rotation:
        return self._rotation

    def setRotation(self, rotation: QPdfDocumentRenderOptions.Rotation) -> None:
        self._rotation = rotation

    def renderFlags(self) -> QPdfDocumentRenderOptions.RenderFlag:
        return self._flags

    def setRenderFlags(self, flags: QPdfDocumentRenderOptions.RenderFlag) -> None:
        self._flags = flags

    def scaledClipRect(self) -> QRectF:
        return self._clip

    def setScaledClipRect(self, rect: QRectF) -> None:
        self._clip = rect


class QPdfDocument(QObject):
    class Status(enum.Enum):
        Null = 0
        Loading = 1
        Ready = 2
        Unloading = 3
        Error = 4

    class Error(enum.Enum):
        None_ = 0
        Unknown = 1
        DataNotYetAvailable = 2
        FileNotFound = 3
        InvalidFileFormat = 4
        IncorrectPassword = 5
        UnsupportedSecurityScheme = 6

    class MetaDataField(enum.Enum):
        Title = 0
        Subject = 1
        Author = 2
        Keywords = 3
        Producer = 4
        Creator = 5
        CreationDate = 6
        ModificationDate = 7

    statusChanged = pyqtSignal(object)
    pageCountChanged = pyqtSignal(int)
    passwordChanged = pyqtSignal()
    pageModelChanged = pyqtSignal()

    _errors = {
        "missing": Error.FileNotFound,
        "format": Error.InvalidFileFormat,
        "password": Error.IncorrectPassword,
    }

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._doc: Any = None
        self._sizes: list[tuple[float, float]] = []
        self._meta: dict[str, Any] = {}
        self._password = ""
        self._status = QPdfDocument.Status.Null
        self._error = QPdfDocument.Error.None_
        # add-ons use a document from worker threads; the backends are not
        # safe for concurrent calls on one document
        self._lock = threading.RLock()

    def _set_status(self, status: QPdfDocument.Status) -> None:
        if status != self._status:
            self._status = status
            self.statusChanged.emit(status)

    def load(self, source: str | QIODevice) -> QPdfDocument.Error:
        self.close()
        if isinstance(source, QIODevice):
            data = bytes(source.readAll())
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(data)
                source = f.name
        self._set_status(QPdfDocument.Status.Loading)
        with self._lock:
            try:
                self._doc = backend.open(str(source), self._password)
                self._sizes = backend.page_sizes(self._doc)
                self._meta = backend.metadata(self._doc)
            except backend.PdfError as e:
                self._doc = None
                self._error = self._errors.get(e.kind, QPdfDocument.Error.Unknown)
            except Exception:
                self._doc = None
                self._error = QPdfDocument.Error.Unknown
            else:
                self._error = QPdfDocument.Error.None_
        if self._doc is None:
            self._set_status(QPdfDocument.Status.Error)
            return self._error
        self._set_status(QPdfDocument.Status.Ready)
        self.pageCountChanged.emit(len(self._sizes))
        return self._error

    def close(self) -> None:
        with self._lock:
            if self._doc is None:
                return
            self._set_status(QPdfDocument.Status.Unloading)
            backend.close(self._doc)
            self._doc = None
            self._sizes = []
            self._meta = {}
        self._error = QPdfDocument.Error.None_
        self.pageCountChanged.emit(0)
        self._set_status(QPdfDocument.Status.Null)

    def status(self) -> QPdfDocument.Status:
        return self._status

    def error(self) -> QPdfDocument.Error:
        return self._error

    def password(self) -> str:
        return self._password

    def setPassword(self, password: str) -> None:
        if password != self._password:
            self._password = password
            self.passwordChanged.emit()

    def resetPassword(self) -> None:
        self.setPassword("")

    def pageCount(self) -> int:
        return len(self._sizes)

    def _valid(self, page: int) -> bool:
        return self._doc is not None and 0 <= page < len(self._sizes)

    def pagePointSize(self, page: int) -> QSizeF:
        if not self._valid(page):
            return QSizeF()
        return QSizeF(*self._sizes[page])

    def pageLabel(self, page: int) -> str:
        return str(page + 1) if self._valid(page) else ""

    def pageIndexForLabel(self, label: str) -> int:
        try:
            page = int(label) - 1
        except ValueError:
            return -1
        return page if self._valid(page) else -1

    def metaData(self, field: QPdfDocument.MetaDataField) -> Any:
        value = self._meta.get(field.name)
        if field in (QPdfDocument.MetaDataField.CreationDate, QPdfDocument.MetaDataField.ModificationDate):
            # the backends give seconds since the epoch
            return QDateTime.fromSecsSinceEpoch(int(value)) if value else QDateTime()
        return value or ""

    def getAllText(self, page: int) -> QPdfSelection:
        if not self._valid(page):
            return QPdfSelection()
        with self._lock:
            return QPdfSelection(backend.text(self._doc, page) or "", 0)

    def getSelectionAtIndex(self, page: int, start: int, maxLength: int) -> QPdfSelection:
        text = self.getAllText(page).text()
        if not 0 <= start < len(text):
            return QPdfSelection()
        return QPdfSelection(text[start : start + maxLength], start)

    def getSelection(self, page: int, start: QPointF, end: QPointF) -> QPdfSelection:
        # no glyph positions from the backends: the whole page's text
        return self.getAllText(page)

    def render(
        self, page: int, imageSize: QSize, options: QPdfDocumentRenderOptions | None = None
    ) -> QImage:
        if not self._valid(page) or imageSize.isEmpty():
            return QImage()
        with self._lock:
            png = backend.render(self._doc, page, imageSize.width(), imageSize.height())
        image = QImage.fromData(png, "PNG") if png else QImage()
        if options is not None and options.rotation() != QPdfDocumentRenderOptions.Rotation.None_:
            from PyQt6.QtGui import QTransform

            image = image.transformed(QTransform().rotate(90 * options.rotation().value))
        return image
