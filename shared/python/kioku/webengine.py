"""QtWebEngine / QtWebChannel API on top of WKWebView.

Qt WebEngine (Chromium) cannot run on iOS, and is not available for Qt on
Android, so the PyQt6.QtWebEngine* modules in these apps are this file, on
top of the platform's own web view (kioku_platform.WebView). It implements the part of the API that
Anki and typical add-ons use; unknown methods are logged and ignored instead
of raising, so an add-on calling something exotic degrades instead of
crashing.
"""

from __future__ import annotations

import enum
import json
import logging
from typing import Any, Callable

from PyQt6.QtCore import (
    QByteArray,
    QEvent,
    QObject,
    QPoint,
    QSize,
    QTimer,
    QUrl,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QAction, QColor, QCursor, QGuiApplication, QIcon
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWidgets import QApplication, QWidget

import kioku_platform as platform

from . import webscripts

logger = logging.getLogger("kioku.webengine")

# Preferences › User interface size (kioku.patches): Qt scales the widgets,
# the pages are zoomed by it on top of their own zoom factor
UI_SCALE = 1.0

_reported: set[str] = set()


class _Lenient:
    """Unknown public methods become logged no-ops returning None."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        key = f"{type(self).__name__}.{name}"
        if key not in _reported:
            _reported.add(key)
            logger.info("unsupported WebEngine API: %s", key)
        return lambda *args, **kwargs: None


# Scripts ---------------------------------------------------------------------


class QWebEngineScript:
    class InjectionPoint(enum.Enum):
        Deferred = 0
        DocumentReady = 1
        DocumentCreation = 2

    class ScriptWorldId(enum.IntEnum):
        MainWorld = 0
        ApplicationWorld = 1
        UserWorld = 2

    def __init__(self, other: QWebEngineScript | None = None) -> None:
        self._source = ""
        self._name = ""
        self._world = 0
        self._injection = QWebEngineScript.InjectionPoint.Deferred
        self._subframes = True
        if other is not None:
            self.__dict__.update(other.__dict__)

    def setSourceCode(self, code: str) -> None:
        self._source = code

    def sourceCode(self) -> str:
        return self._source

    def setSourceUrl(self, url: QUrl) -> None:
        path = url.toLocalFile() or url.path()
        try:
            with open(path, encoding="utf8") as f:
                self._source = f.read()
        except OSError:
            logger.warning("cannot read script %s", url.toString())

    def setName(self, name: str) -> None:
        self._name = name

    def name(self) -> str:
        return self._name

    def setWorldId(self, world: int) -> None:
        self._world = int(world)

    def worldId(self) -> int:
        return self._world

    def setInjectionPoint(self, point: QWebEngineScript.InjectionPoint) -> None:
        self._injection = point

    def injectionPoint(self) -> QWebEngineScript.InjectionPoint:
        return self._injection

    def setRunsOnSubFrames(self, on: bool) -> None:
        self._subframes = on

    def runsOnSubFrames(self) -> bool:
        return self._subframes

    def isNull(self) -> bool:
        return not self._source

    def _for_webkit(self) -> tuple[str, int, bool]:
        point = self._injection
        source = self._source
        if point == QWebEngineScript.InjectionPoint.DocumentCreation:
            when = webscripts.AT_DOCUMENT_START
        else:
            when = webscripts.AT_DOCUMENT_END
            if point == QWebEngineScript.InjectionPoint.Deferred:
                source = (
                    "(function(){var f=function(){\n"
                    + source
                    + "\n};if(document.readyState==='complete'){f();}"
                    "else{window.addEventListener('load',f);}})();"
                )
        return (source, when, not self._subframes)


class QWebEngineScriptCollection:
    def __init__(self) -> None:
        self._scripts: list[QWebEngineScript] = []

    def insert(self, script: QWebEngineScript | list[QWebEngineScript]) -> None:
        scripts = script if isinstance(script, list) else [script]
        for s in scripts:
            if s not in self._scripts:
                self._scripts.append(s)

    def contains(self, script: QWebEngineScript) -> bool:
        return script in self._scripts

    def remove(self, script: QWebEngineScript) -> bool:
        if script in self._scripts:
            self._scripts.remove(script)
            return True
        return False

    def find(self, name: str) -> list[QWebEngineScript]:
        return [s for s in self._scripts if s.name() == name]

    def findScript(self, name: str) -> QWebEngineScript:
        found = self.find(name)
        return found[0] if found else QWebEngineScript()

    def toList(self) -> list[QWebEngineScript]:
        return list(self._scripts)

    def clear(self) -> None:
        self._scripts.clear()

    def count(self) -> int:
        return len(self._scripts)

    def isEmpty(self) -> bool:
        return not self._scripts


# Settings --------------------------------------------------------------------


class QWebEngineSettings(_Lenient):
    class WebAttribute(enum.Enum):
        AutoLoadImages = 0
        JavascriptEnabled = 1
        JavascriptCanOpenWindows = 2
        JavascriptCanAccessClipboard = 3
        LinksIncludedInFocusChain = 4
        LocalStorageEnabled = 5
        LocalContentCanAccessRemoteUrls = 6
        XSSAuditingEnabled = 7
        SpatialNavigationEnabled = 8
        LocalContentCanAccessFileUrls = 9
        HyperlinkAuditingEnabled = 10
        ScrollAnimatorEnabled = 11
        ErrorPageEnabled = 12
        PluginsEnabled = 13
        FullScreenSupportEnabled = 14
        ScreenCaptureEnabled = 15
        WebGLEnabled = 16
        Accelerated2dCanvasEnabled = 17
        AutoLoadIconsForPage = 18
        TouchIconsEnabled = 19
        FocusOnNavigationEnabled = 20
        PrintElementBackgrounds = 21
        AllowRunningInsecureContent = 22
        AllowGeolocationOnInsecureOrigins = 23
        AllowWindowActivationFromJavaScript = 24
        ShowScrollBars = 25
        PlaybackRequiresUserGesture = 26
        WebRTCPublicInterfacesOnly = 27
        JavascriptCanPaste = 28
        DnsPrefetchEnabled = 29
        PdfViewerEnabled = 30
        NavigateOnDropEnabled = 31
        ReadingFromCanvasEnabled = 32
        ForceDarkMode = 33
        PrintHeaderAndFooter = 34
        PreferCSSMarginsForPrinting = 35
        TouchEventsApiEnabled = 36

    class FontFamily(enum.Enum):
        StandardFont = 0
        FixedFont = 1
        SerifFont = 2
        SansSerifFont = 3
        CursiveFont = 4
        FantasyFont = 5
        PictographFont = 6

    class FontSize(enum.Enum):
        MinimumFontSize = 0
        MinimumLogicalFontSize = 1
        DefaultFontSize = 2
        DefaultFixedFontSize = 3

    class UnknownUrlSchemePolicy(enum.Enum):
        DisallowUnknownUrlSchemes = 1
        AllowUnknownUrlSchemesFromUserInteraction = 2
        AllowAllUnknownUrlSchemes = 3

    def __init__(self) -> None:
        self._attributes: dict[Any, bool] = {}
        self._fonts: dict[Any, str] = {}
        self._sizes: dict[Any, int] = {}

    def setAttribute(self, attr: Any, on: bool) -> None:
        self._attributes[attr] = on

    def testAttribute(self, attr: Any) -> bool:
        return self._attributes.get(attr, True)

    def resetAttribute(self, attr: Any) -> None:
        self._attributes.pop(attr, None)

    def setFontFamily(self, which: Any, family: str) -> None:
        self._fonts[which] = family

    def fontFamily(self, which: Any) -> str:
        return self._fonts.get(which, "")

    def setFontSize(self, which: Any, size: int) -> None:
        self._sizes[which] = size

    def fontSize(self, which: Any) -> int:
        return self._sizes.get(which, 16)


# Profile ---------------------------------------------------------------------


class QWebEngineUrlRequestInterceptor(QObject):
    def interceptRequest(self, info: Any) -> None:
        pass


class _RequestInfo:
    """Just enough of QWebEngineUrlRequestInfo to collect extra headers."""

    def __init__(self, url: QUrl) -> None:
        self._url = url
        self.headers: dict[str, str] = {}
        self.blocked = False

    def requestUrl(self) -> QUrl:
        return self._url

    def firstPartyUrl(self) -> QUrl:
        return self._url

    def requestMethod(self) -> QByteArray:
        return QByteArray(b"GET")

    def setHttpHeader(self, name: bytes | QByteArray, value: bytes | QByteArray) -> None:
        self.headers[bytes(name).decode()] = bytes(value).decode()

    def block(self, shouldBlock: bool) -> None:
        self.blocked = shouldBlock

    def redirect(self, url: QUrl) -> None:
        pass

    def resourceType(self) -> int:
        return 0

    def navigationType(self) -> int:
        return 0


class QWebEngineProfile(QObject, _Lenient):
    class HttpCacheType(enum.Enum):
        MemoryHttpCache = 0
        DiskHttpCache = 1
        NoCache = 2

    class PersistentCookiesPolicy(enum.Enum):
        NoPersistentCookies = 0
        AllowPersistentCookies = 1
        ForcePersistentCookies = 2

    downloadRequested = pyqtSignal(object)
    _default: QWebEngineProfile | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # QWebEngineProfile(parent=None) or (storageName, parent=None)
        parent = kwargs.get("parent")
        if parent is None:
            parent = next((a for a in args if isinstance(a, QObject)), None)
        name = kwargs.get("storageName")
        if name is None:
            name = next((a for a in args if isinstance(a, str)), "")
        super().__init__(parent)
        self._storage_name = name
        self._scripts = QWebEngineScriptCollection()
        self._settings = QWebEngineSettings()
        self._interceptor: QWebEngineUrlRequestInterceptor | None = None
        self._user_agent = ""
        self._cookies = QWebEngineCookieStore(self)

    @classmethod
    def defaultProfile(cls) -> QWebEngineProfile:
        if cls._default is None:
            cls._default = QWebEngineProfile()
        return cls._default

    def scripts(self) -> QWebEngineScriptCollection:
        return self._scripts

    def settings(self) -> QWebEngineSettings:
        return self._settings

    def setUrlRequestInterceptor(self, interceptor: Any) -> None:
        self._interceptor = interceptor

    def urlRequestInterceptor(self) -> Any:
        return self._interceptor

    def setHttpUserAgent(self, agent: str) -> None:
        self._user_agent = agent

    def httpUserAgent(self) -> str:
        return self._user_agent

    def isOffTheRecord(self) -> bool:
        return not self._storage_name

    def storageName(self) -> str:
        return self._storage_name

    def cookieStore(self) -> QWebEngineCookieStore:
        return self._cookies

    def _headers_for(self, url: QUrl) -> dict[str, str]:
        if self._interceptor is None:
            return {}
        info = _RequestInfo(url)
        try:
            self._interceptor.interceptRequest(info)
        except Exception:
            logger.exception("request interceptor")
        return info.headers


# Page ------------------------------------------------------------------------


class QWebEnginePage(QObject, _Lenient):
    class WebAction(enum.Enum):
        NoWebAction = -1
        Back = 0
        Forward = 1
        Stop = 2
        Reload = 3
        Cut = 4
        Copy = 5
        Paste = 6
        Undo = 7
        Redo = 8
        SelectAll = 9
        ReloadAndBypassCache = 10
        PasteAndMatchStyle = 11
        OpenLinkInThisWindow = 12
        OpenLinkInNewWindow = 13
        OpenLinkInNewTab = 14
        CopyLinkToClipboard = 15
        DownloadLinkToDisk = 16
        CopyImageToClipboard = 17
        CopyImageUrlToClipboard = 18
        DownloadImageToDisk = 19
        CopyMediaUrlToClipboard = 20
        ToggleMediaControls = 21
        ToggleMediaLoop = 22
        ToggleMediaPlayPause = 23
        ToggleMediaMute = 24
        DownloadMediaToDisk = 25
        InspectElement = 26
        ExitFullScreen = 27
        RequestClose = 28
        Unselect = 29
        SavePage = 30
        OpenLinkInNewBackgroundTab = 31
        ViewSource = 32
        ToggleStrikethrough = 33
        ToggleBold = 34
        ToggleItalic = 35
        ToggleUnderline = 36

    class JavaScriptConsoleMessageLevel(enum.Enum):
        InfoMessageLevel = 0
        WarningMessageLevel = 1
        ErrorMessageLevel = 2

    class NavigationType(enum.Enum):
        NavigationTypeLinkClicked = 0
        NavigationTypeTyped = 1
        NavigationTypeFormSubmitted = 2
        NavigationTypeBackForward = 3
        NavigationTypeReload = 4
        NavigationTypeOther = 5
        NavigationTypeRedirect = 6

    class WebWindowType(enum.Enum):
        WebBrowserWindow = 0
        WebBrowserTab = 1
        WebDialog = 2
        WebBrowserBackgroundTab = 3

    class FindFlag(enum.Flag):
        FindBackward = 1
        FindCaseSensitively = 2

    class Feature(enum.Enum):
        Notifications = 0
        Geolocation = 1
        MediaAudioCapture = 2
        MediaVideoCapture = 3
        MediaAudioVideoCapture = 4
        MouseLock = 5
        DesktopVideoCapture = 6
        DesktopAudioVideoCapture = 7
        ClipboardReadWrite = 8
        LocalFontsAccess = 9

    class PermissionPolicy(enum.Enum):
        PermissionUnknown = 0
        PermissionGrantedByUser = 1
        PermissionDeniedByUser = 2

    class RenderProcessTerminationStatus(enum.Enum):
        NormalTerminationStatus = 0
        AbnormalTerminationStatus = 1
        CrashedTerminationStatus = 2
        KilledTerminationStatus = 3

    loadStarted = pyqtSignal()
    loadProgress = pyqtSignal(int)
    loadFinished = pyqtSignal(bool)
    titleChanged = pyqtSignal(str)
    urlChanged = pyqtSignal(QUrl)
    selectionChanged = pyqtSignal()
    contentsSizeChanged = pyqtSignal(object)
    scrollPositionChanged = pyqtSignal(object)
    windowCloseRequested = pyqtSignal()
    featurePermissionRequested = pyqtSignal(QUrl, object)
    renderProcessTerminated = pyqtSignal(object, int)
    pdfPrintingFinished = pyqtSignal(str, bool)

    # WKNavigationType -> Qt navigation type
    _NAV_TYPES = {0: 0, 1: 2, 2: 3, 3: 4, 4: 2, -1: 5}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # QWebEnginePage(parent=None) or (profile, parent=None)
        profile = kwargs.get("profile")
        if profile is None:
            profile = next((a for a in args if isinstance(a, QWebEngineProfile)), None)
        parent = kwargs.get("parent")
        if parent is None:
            parent = next(
                (a for a in args if isinstance(a, QObject) and a is not profile), None
            )
        super().__init__(parent)
        self._profile = profile or QWebEngineProfile.defaultProfile()
        self._history = QWebEngineHistory(self)
        self._settings = QWebEngineSettings()
        self._scripts = QWebEngineScriptCollection()
        self._channel: QWebChannel | None = None
        self._selection = ""
        self._zoom = 1.0
        self._background = QColor(Qt.GlobalColor.white)
        self._view: QWebEngineView | None = None
        self._web = platform.WebView()
        self._last_load: tuple[str, dict[str, str]] | None = None
        self._retried = False
        # (shown, requested) while load() runs: the platform views report the
        # requested URL at once, Qt only once the new page is there
        self._loading: tuple[QUrl, QUrl] | None = None
        self._web.on_console = self._on_console  # type: ignore[method-assign]
        self._web.on_selection = self._on_selection  # type: ignore[method-assign]
        self._web.on_tap = self._on_tap  # type: ignore[method-assign]
        self._web.on_pdf_finished = self.pdfPrintingFinished.emit  # type: ignore[method-assign]
        self._web.on_channel_call = self._on_channel_call  # type: ignore[method-assign]
        self._web.on_navigation = self._on_navigation  # type: ignore[method-assign]
        self._web.on_load_started = self.loadStarted.emit  # type: ignore[method-assign]
        self._web.on_load_finished = self._on_load_finished  # type: ignore[method-assign]
        self._web.on_alert = self._on_alert  # type: ignore[method-assign]
        self._web.on_confirm = self._on_confirm  # type: ignore[method-assign]
        self.destroyed.connect(self._web.close)
        if UI_SCALE != 1.0:
            self._web.set_zoom(UI_SCALE)

    # Configuration ---------------------------------------------------------

    def profile(self) -> QWebEngineProfile:
        return self._profile

    def settings(self) -> QWebEngineSettings:
        return self._settings

    def scripts(self) -> QWebEngineScriptCollection:
        return self._scripts

    def setWebChannel(self, channel: QWebChannel, worldId: int = 0) -> None:
        self._channel = channel

    def webChannel(self) -> QWebChannel | None:
        return self._channel

    def setBackgroundColor(self, color: QColor) -> None:
        self._background = QColor(color)
        self._web.set_background(
            color.redF(), color.greenF(), color.blueF(), color.alphaF()
        )

    def backgroundColor(self) -> QColor:
        return self._background

    def setZoomFactor(self, factor: float) -> None:
        self._zoom = factor
        self._web.set_zoom(factor * UI_SCALE)

    def zoomFactor(self) -> float:
        return self._zoom

    def view(self) -> QWebEngineView | None:
        return self._view

    def history(self) -> QWebEngineHistory:
        return self._history

    # Loading ---------------------------------------------------------------

    def _install_scripts(self) -> None:
        scripts = self._profile.scripts().toList() + self._scripts.toList()
        start, end = webscripts.AT_DOCUMENT_START, webscripts.AT_DOCUMENT_END
        converted = [
            (platform.WebView.BRIDGE, start, False),
            (webscripts.PRELUDE, start, False),
            (webscripts.VIEWPORT, end, True),
        ]
        headers = self._profile._headers_for(_media_server_url())
        if headers:
            converted.append((_auth_script(headers), start, False))
        converted += [s._for_webkit() for s in scripts if s.sourceCode()]
        self._web.set_user_scripts(converted)

    def load(self, url: QUrl | str) -> None:
        qurl = QUrl(url) if isinstance(url, str) else url
        self._install_scripts()
        self._last_load = (qurl.toString(), self._profile._headers_for(qurl))
        self._retried = False
        self._loading = (self.url(), qurl)
        self._web.load_url(*self._last_load)

    def setUrl(self, url: QUrl) -> None:
        self.load(url)

    def setHtml(self, html: str, baseUrl: QUrl = QUrl()) -> None:
        self._install_scripts()
        base = baseUrl.toString() if baseUrl and not baseUrl.isEmpty() else None
        self._last_load = None
        self._web.load_html(webscripts.with_viewport(html), base)

    def setContent(
        self, data: Any, mimeType: str = "", baseUrl: QUrl = QUrl()
    ) -> None:
        self.setHtml(bytes(data).decode("utf8", "replace"), baseUrl)

    def url(self) -> QUrl:
        if self._loading is not None:
            return self._loading[0]
        return QUrl(self._web.url())

    def requestedUrl(self) -> QUrl:
        if self._loading is not None:
            return self._loading[1]
        return self.url()

    def title(self) -> str:
        return self._web.title()

    def triggerAction(self, action: Any, checked: bool = False) -> None:
        A = QWebEnginePage.WebAction
        if action == A.Copy or action == A.CopyImageToClipboard:
            text = self._selection
            if text:
                QGuiApplication.clipboard().setText(text)
            else:
                self._exec_command("copy")
        elif action == A.Cut:
            if self._selection:
                QGuiApplication.clipboard().setText(self._selection)
            self._exec_command("delete")
        elif action in (A.Paste, A.PasteAndMatchStyle):
            mime = QGuiApplication.clipboard().mimeData()
            if mime is not None and mime.hasHtml() and action == A.Paste:
                self.runJavaScript(
                    f"document.execCommand('insertHTML', false, {json.dumps(mime.html())})"
                )
            elif mime is not None and mime.hasText():
                self.runJavaScript(
                    f"document.execCommand('insertText', false, {json.dumps(mime.text())})"
                )
        elif action == A.SelectAll:
            self._exec_command("selectAll")
        elif action == A.Undo:
            self._exec_command("undo")
        elif action == A.Redo:
            self._exec_command("redo")
        elif action == A.Unselect:
            self.runJavaScript("window.getSelection().removeAllRanges()")
        elif action == A.ToggleBold:
            self._exec_command("bold")
        elif action == A.ToggleItalic:
            self._exec_command("italic")
        elif action == A.ToggleUnderline:
            self._exec_command("underline")
        elif action == A.ToggleStrikethrough:
            self._exec_command("strikeThrough")
        elif action == A.Back:
            self._web.back()
        elif action == A.Forward:
            self._web.forward()
        elif action in (A.Reload, A.ReloadAndBypassCache):
            self._web.reload()
        elif action == A.Stop:
            self._web.stop()
        else:
            logger.info("unsupported web action %s", action)

    def _exec_command(self, name: str) -> None:
        self.runJavaScript(f"document.execCommand({json.dumps(name)})")

    def action(self, action: Any) -> QAction:
        a = QAction(self)
        a.triggered.connect(lambda: self.triggerAction(action))
        return a

    def hasSelection(self) -> bool:
        return bool(self._selection)

    def selectedText(self) -> str:
        return self._selection

    def findText(self, text: str, options: Any = None, resultCallback: Any = None) -> None:
        backwards = bool(options) and bool(
            options & QWebEnginePage.FindFlag.FindBackward
        )
        self.runJavaScript(
            f"window.find({json.dumps(text)}, false, {json.dumps(backwards)})",
            lambda found: resultCallback(found) if resultCallback else None,
        )

    def runJavaScript(self, script: str, *args: Any) -> None:
        callback = next((a for a in args if callable(a)), None)
        if callback is None:
            self._web.evaluate(script, None)
        else:
            self._web.evaluate(script, lambda value: callback(_qt_value(value)))

    def printToPdf(self, path: Any, *args: Any) -> None:
        """Only the file form (Anki's Statistics → Save PDF); the page layout
        argument is ignored."""
        print_pdf = getattr(self._web, "print_pdf", None)
        if print_pdf is None or not isinstance(path, str):
            logger.info("printToPdf is not supported on this platform")
            return
        print_pdf(path)

    # Overridable hooks -----------------------------------------------------

    def acceptNavigationRequest(self, url: QUrl, navType: Any, isMainFrame: bool) -> bool:
        return True

    def javaScriptConsoleMessage(
        self, level: Any, message: str, lineNumber: int, sourceID: str
    ) -> None:
        print(f"JS {level.name}: {message}")

    def javaScriptAlert(self, securityOrigin: QUrl, msg: str) -> None:
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.information(self._view, "", msg)

    def javaScriptConfirm(self, securityOrigin: QUrl, msg: str) -> bool:
        from PyQt6.QtWidgets import QMessageBox

        return (
            QMessageBox.question(self._view, "", msg)
            == QMessageBox.StandardButton.Yes
        )

    def createWindow(self, type: Any) -> QWebEnginePage | None:
        return None

    # From WebKit -----------------------------------------------------------

    def _on_console(self, entry: dict) -> None:
        L = QWebEnginePage.JavaScriptConsoleMessageLevel
        level = {
            "warn": L.WarningMessageLevel,
            "error": L.ErrorMessageLevel,
        }.get(entry.get("level", ""), L.InfoMessageLevel)
        try:
            self.javaScriptConsoleMessage(
                level, entry.get("msg", ""), 0, entry.get("src", "")
            )
        except Exception:
            logger.exception("javaScriptConsoleMessage")

    def _on_selection(self, text: str) -> None:
        changed = text != self._selection
        self._selection = text
        if changed:
            self.selectionChanged.emit()
            if self._view is not None:
                self._view.selectionChanged.emit()

    def _on_tap(self, x: float, y: float) -> None:
        global _tap
        if self._view is not None:
            view = self._view
            at = QPoint(round(x * view.width()), round(y * view.height()))
            _tap = (view.mapToGlobal(at), _qt_cursor_pos())

    def _on_channel_call(self, obj: str, method: str, args: list) -> Any:
        if self._channel is None:
            raise RuntimeError("no web channel")
        target = self._channel._objects.get(obj)
        if target is None:
            raise RuntimeError(f"no object {obj!r} registered")
        return getattr(target, method)(*args)

    def _on_navigation(self, url: str, nav_type: int, main_frame: bool) -> bool:
        if url.startswith("about:"):
            return True
        nav = QWebEnginePage.NavigationType(self._NAV_TYPES.get(nav_type, 5))
        return bool(self.acceptNavigationRequest(QUrl(url), nav, main_frame))

    def _on_load_finished(self, ok: bool) -> None:
        if not ok and self._retry_local_load():
            return
        if self._loading is not None:
            shown = self._loading[0]
            self._loading = None
            if self.url() != shown:
                self.urlChanged.emit(self.url())
        self.loadProgress.emit(100)
        self.loadFinished.emit(ok)
        self.titleChanged.emit(self._web.title())
        if self._view is not None:
            self._view._page_load_finished(ok)

    def _retry_local_load(self) -> bool:
        """A page from Anki's media server failed: the server may have lost
        its socket while the app was in the background. Restart it and try
        once more."""
        if self._last_load is None or self._retried:
            return False
        if QUrl(self._last_load[0]).host() != "127.0.0.1":
            return False
        from . import mediaserver

        self._retried = True
        mediaserver.ensure_running()
        url = QUrl(self._last_load[0])
        url.setPort(mediaserver.current_port() or url.port())
        last = (url.toString(), self._last_load[1])
        QTimer.singleShot(200, lambda: self._web.load_url(*last))
        return True

    def _on_alert(self, text: str) -> None:
        # the JS side has already continued; show the message on the next tick
        QTimer.singleShot(0, lambda: self.javaScriptAlert(self.url(), text))

    def _on_confirm(self, text: str) -> bool:
        return bool(self.javaScriptConfirm(self.url(), text))


def _qt_value(value: Any) -> Any:
    """Qt WebEngine returns whole JavaScript numbers as ints (Anki passes
    them to setFixedHeight() and the like); WebKit returns every number as a
    double."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_qt_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _qt_value(v) for k, v in value.items()}
    return value


def _media_server_url() -> QUrl:
    """Anki's local web server, to ask the request interceptor about: since
    26.09 it adds its headers only to URLs with the server's host and port."""
    import aqt

    if getattr(aqt.mw, "mediaServer", None) is None:
        return QUrl("http://127.0.0.1/")
    return QUrl(aqt.mw.serverURL())


def _auth_script(headers: dict[str, str]) -> str:
    """Add the interceptor's headers to fetch/XHR requests to 127.0.0.1,
    which WebKit has no request interceptor for."""
    return (
        "(function(h){"
        "function local(u){try{return new URL(u,location.href).hostname==='127.0.0.1';}"
        "catch(e){return false;}}"
        "var of=window.fetch;"
        "window.fetch=function(input,init){"
        "var u=(typeof input==='string'||input instanceof URL)?String(input):input.url;"
        "if(local(u)){init=Object.assign({},init||{});"
        "var hd=new Headers(init.headers||(input&&input.headers)||{});"
        "for(var k in h){hd.set(k,h[k]);}init.headers=hd;}"
        "return of.call(this,input,init);};"
        "var oo=XMLHttpRequest.prototype.open,os=XMLHttpRequest.prototype.send;"
        "XMLHttpRequest.prototype.open=function(m,u){this.__kiokuUrl=String(u);"
        "return oo.apply(this,arguments);};"
        "XMLHttpRequest.prototype.send=function(){"
        "if(local(this.__kiokuUrl)){for(var k in h){this.setRequestHeader(k,h[k]);}}"
        "return os.apply(this,arguments);};"
        f"}})({json.dumps(headers)});"
    )


# View ------------------------------------------------------------------------


class _PopupWatcher(QObject):
    """Qt closes a popup (a menu, a combo box's list) on a tap outside it,
    but taps on a page go to the native web view, not to Qt: the review
    screen's More menu could not be closed on an iPad. While a popup is
    open, the web views leave taps to Qt (kioku_platform.WebView)."""

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._touchable = True
        app.installEventFilter(self)

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if (
            event is not None
            and event.type() in (QEvent.Type.Show, QEvent.Type.Hide)
            and isinstance(obj, QWidget)
            and obj.windowType() == Qt.WindowType.Popup
        ):
            # the popup list changes after the event
            QTimer.singleShot(0, self._update)
        return False

    def _update(self) -> None:
        touchable = QApplication.activePopupWidget() is None
        if touchable != self._touchable:
            self._touchable = touchable
            platform.WebView.set_touchable(touchable)


_popup_watcher: _PopupWatcher | None = None


# Where a page was last tapped, and what Qt's QCursor.pos() said then
_tap: tuple[QPoint, QPoint] | None = None
_qt_cursor_pos = QCursor.pos


def _cursor_pos(*args: Any) -> QPoint:
    """Taps on a page go to the native web view, so Qt's cursor stays where
    Qt last saw a tap: Anki opens menus at QCursor.pos() (the review
    screen's More), and they showed at the top left. Until Qt sees a tap
    again, the cursor is where the page was tapped."""
    qt = _qt_cursor_pos(*args)
    if _tap is not None and qt == _tap[1]:
        return QPoint(_tap[0])
    return qt


QCursor.pos = staticmethod(_cursor_pos)  # type: ignore[method-assign]


class QWebEngineView(QWidget, _Lenient):
    loadStarted = pyqtSignal()
    loadProgress = pyqtSignal(int)
    loadFinished = pyqtSignal(bool)
    titleChanged = pyqtSignal(str)
    urlChanged = pyqtSignal(QUrl)
    selectionChanged = pyqtSignal()
    iconChanged = pyqtSignal(QIcon)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        parent = kwargs.pop("parent", None)
        for a in args:
            if isinstance(a, QWidget):
                parent = a
        super().__init__(parent)
        global _popup_watcher
        if _popup_watcher is None:
            _popup_watcher = _PopupWatcher(QApplication.instance())
        platform.WebView.prepare_host(self)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._page: QWebEnginePage | None = None
        self._own_page = False

    def page(self) -> QWebEnginePage:
        if self._page is None:
            self.setPage(QWebEnginePage(self))
            self._own_page = True
        assert self._page is not None
        return self._page

    def setPage(self, page: QWebEnginePage) -> None:
        if self._page is not None and self._page is not page:
            self._page._web.detach()
            self._page._view = None
        self._page = page
        page._view = self
        page.loadStarted.connect(self.loadStarted)
        page.loadProgress.connect(self.loadProgress)
        page.titleChanged.connect(self.titleChanged)
        page.urlChanged.connect(self.urlChanged)
        self._attach()

    def _page_load_finished(self, ok: bool) -> None:
        self.loadFinished.emit(ok)

    def _attach(self) -> None:
        if self._page is None or not self.isVisible():
            return
        try:
            self._page._web.attach(self)
        except Exception:
            logger.exception("attaching web view")

    def event(self, evt: QEvent | None) -> bool:
        if evt is not None and evt.type() in (
            QEvent.Type.WinIdChange,
            QEvent.Type.Show,
            QEvent.Type.ParentChange,
        ):
            QTimer.singleShot(0, self._attach)
        return super().event(evt)

    def sizeHint(self) -> QSize:
        return QSize(400, 300)

    def focusProxy(self) -> QWidget:
        return self

    # Convenience wrappers around the page ----------------------------------

    def load(self, url: QUrl | str) -> None:
        self.page().load(url)

    def setUrl(self, url: QUrl) -> None:
        self.page().load(url)

    def url(self) -> QUrl:
        return self.page().url()

    def setHtml(self, html: str, baseUrl: QUrl = QUrl()) -> None:
        self.page().setHtml(html, baseUrl)

    def setContent(self, data: Any, mimeType: str = "", baseUrl: QUrl = QUrl()) -> None:
        self.page().setContent(data, mimeType, baseUrl)

    def title(self) -> str:
        return self.page().title()

    def settings(self) -> QWebEngineSettings:
        return self.page().settings()

    def triggerPageAction(self, action: Any, checked: bool = False) -> None:
        self.page().triggerAction(action, checked)

    def pageAction(self, action: Any) -> QAction:
        return self.page().action(action)

    def hasSelection(self) -> bool:
        return self.page().hasSelection()

    def selectedText(self) -> str:
        return self.page().selectedText()

    def setZoomFactor(self, factor: float) -> None:
        self.page().setZoomFactor(factor)

    def zoomFactor(self) -> float:
        return self.page().zoomFactor()

    def findText(self, text: str, options: Any = None, resultCallback: Any = None) -> None:
        self.page().findText(text, options, resultCallback)

    def reload(self) -> None:
        self.page()._web.reload()

    def stop(self) -> None:
        self.page()._web.stop()

    def back(self) -> None:
        self.page()._web.back()

    def forward(self) -> None:
        self.page()._web.forward()

    def createWindow(self, type: Any) -> QWebEngineView | None:
        return None

    def printToPdf(self, *args: Any) -> None:
        self.page().printToPdf(*args)

    @staticmethod
    def forPage(page: QWebEnginePage) -> QWebEngineView | None:
        return page.view()


# Web channel -----------------------------------------------------------------


class QWebChannel(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._objects: dict[str, QObject] = {}

    def registerObject(self, name: str, obj: QObject) -> None:
        self._objects[name] = obj

    def registerObjects(self, objects: dict[str, QObject]) -> None:
        self._objects.update(objects)

    def deregisterObject(self, obj: QObject) -> None:
        for name, value in list(self._objects.items()):
            if value is obj:
                del self._objects[name]

    def registeredObjects(self) -> dict[str, QObject]:
        return dict(self._objects)

    def setBlockUpdates(self, block: bool) -> None:
        pass

    def blockUpdates(self) -> bool:
        return False


# Misc classes add-ons sometimes import -----------------------------------------


class QWebEngineDownloadRequest(QObject, _Lenient):
    pass


class QWebEngineContextMenuRequest(QObject, _Lenient):
    pass


class QWebEngineUrlScheme(_Lenient):
    @staticmethod
    def registerScheme(scheme: Any) -> None:
        pass


class QWebEngineUrlSchemeHandler(QObject, _Lenient):
    pass


class QWebEngineCookieStore(QObject, _Lenient):
    """All profiles share the platform web view's cookie jar, so a store only
    knows the cookies set through it; deleteAllCookies() removes those and
    whatever the web pages set on the same domains."""

    cookieAdded = pyqtSignal(QNetworkCookie)
    cookieRemoved = pyqtSignal(QNetworkCookie)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._known: dict[tuple[str, str, str], QNetworkCookie] = {}

    @staticmethod
    def _key(cookie: QNetworkCookie) -> tuple[str, str, str]:
        return (bytes(cookie.name()).decode(), cookie.domain(), cookie.path())

    @staticmethod
    def _url_for(cookie: QNetworkCookie, origin: QUrl) -> str:
        if not origin.isEmpty():
            return origin.toString()
        return f"https://{cookie.domain().lstrip('.')}{cookie.path() or '/'}"

    def setCookie(self, cookie: QNetworkCookie, origin: QUrl = QUrl()) -> None:
        cookie = QNetworkCookie(cookie)
        if not cookie.domain() and not origin.isEmpty():
            cookie.setDomain(origin.host())
        if not cookie.domain():
            logger.warning("cookie without domain or origin ignored")
            return
        raw = bytes(cookie.toRawForm(QNetworkCookie.RawForm.Full)).decode()
        platform.set_cookie(self._url_for(cookie, origin), raw)
        self._known[self._key(cookie)] = cookie
        self.cookieAdded.emit(cookie)

    def deleteCookie(self, cookie: QNetworkCookie, origin: QUrl = QUrl()) -> None:
        domain = cookie.domain() or origin.host()
        platform.delete_cookies(domain, bytes(cookie.name()).decode())
        removed = self._known.pop(self._key(cookie), None)
        self.cookieRemoved.emit(removed or cookie)

    def deleteAllCookies(self) -> None:
        for domain in {c.domain() for c in self._known.values()}:
            platform.delete_cookies(domain, None)
        for cookie in list(self._known.values()):
            self.cookieRemoved.emit(cookie)
        self._known.clear()

    def deleteSessionCookies(self) -> None:
        for key, cookie in list(self._known.items()):
            if cookie.isSessionCookie():
                self.deleteCookie(cookie)

    def loadAllCookies(self) -> None:
        for cookie in list(self._known.values()):
            self.cookieAdded.emit(cookie)

    def setCookieFilter(self, filter: Any = None) -> None:
        pass


class QWebEngineHistoryItem:
    def __init__(self, url: str = "") -> None:
        self._url = QUrl(url)

    def url(self) -> QUrl:
        return QUrl(self._url)

    def originalUrl(self) -> QUrl:
        return QUrl(self._url)

    def title(self) -> str:
        return ""

    def isValid(self) -> bool:
        return not self._url.isEmpty()


class QWebEngineHistory(_Lenient):
    """Back/forward state of a page, read from the platform web view."""

    def __init__(self, page: QWebEnginePage) -> None:
        self._page = page

    def _state(self) -> dict:
        try:
            return self._page._web.history()
        except Exception:
            logger.exception("reading web view history")
            return {}

    def canGoBack(self) -> bool:
        return bool(self._state().get("back"))

    def canGoForward(self) -> bool:
        return bool(self._state().get("forward"))

    def backItem(self) -> QWebEngineHistoryItem:
        return QWebEngineHistoryItem(self._state().get("back") or "")

    def forwardItem(self) -> QWebEngineHistoryItem:
        return QWebEngineHistoryItem(self._state().get("forward") or "")

    def currentItem(self) -> QWebEngineHistoryItem:
        return QWebEngineHistoryItem(self._page.url().toString())

    def back(self) -> None:
        self._page._web.back()

    def forward(self) -> None:
        self._page._web.forward()


class QWebEngineFindTextResult(_Lenient):
    pass


class QWebEngineNewWindowRequest(QObject, _Lenient):
    pass


class QWebEngineFullScreenRequest(_Lenient):
    pass


class QWebEngineCertificateError(_Lenient):
    pass


def qWebEngineVersion() -> str:
    return "0 (WKWebView)"


def qWebEngineChromiumVersion() -> str:
    return "0"
