"""Web platform layer for the shared kioku package: Anki's pages in
<iframe>s served through a service worker (webview.py, http.py), files
through the browser (files.py), audio and TTS through the page (audio.py).
/home/web_user is kept in IndexedDB (src/main.cpp kioku_load_storage).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from . import web
from .files import pick_files, save_path
from .webview import WebView, delete_cookies, set_cookie

logger = logging.getLogger("kioku.platform")

HOME = os.path.expanduser("~")
FONTS = "/fonts"


def prepare() -> None:
    """Runs before Anki is imported."""
    from PyQt6.QtCore import QCoreApplication, Qt

    from . import http

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar)
    # roots for rustls (reqwest with native roots, which reads this file):
    # the wasm file system has no system store
    os.environ.setdefault("SSL_CERT_FILE", "/site/certifi/cacert.pem")
    _ignore_socket_options()
    _start_threads_yielding()
    web.start()
    _set_timezone()
    http.setup(web.js("origin"))
    _add_fonts()
    _frameless_windows()
    _fill_screen()
    _save_after_changes()
    _follow_theme()
    if dev_allowed():
        web.listen("devexec", _devexec)


def _set_timezone() -> None:
    """Python's time functions follow the browser's zone (Emscripten asks
    JavaScript), but Anki's Rust core (chrono) reads /etc/localtime, which
    the wasm file system lacks, so it ran on UTC: Browse's dates were off and
    the scheduler's day started at the cutoff hour in UTC. Copy the
    browser's zone there from tzdata (tools/fetch_deps.sh) before the
    backend starts."""
    import shutil

    zone = web.js("timeZone")
    path = os.path.join("/site/tzdata/zoneinfo", *zone.split("/"))
    if not zone or ".." in zone or not os.path.isfile(path):
        logger.warning("time zone %r not found; Anki's core uses UTC", zone)
        return
    os.makedirs("/etc", exist_ok=True)
    shutil.copyfile(path, "/etc/localtime")


def _add_fonts() -> None:
    """Qt for WebAssembly brings only DejaVu, so Chinese, Japanese, Korean,
    Thai and Indic text showed as boxes (the language list, Browse). The
    Noto fonts in kioku.data (tools/fetch_deps.sh) are added once Anki's
    QApplication exists, before its first dialog, as the fallback for
    their scripts."""
    import aqt
    from PyQt6.QtCore import QChar
    from PyQt6.QtGui import QFontDatabase

    fallbacks = {
        "Noto Sans SC": ("Han", "Hiragana", "Katakana", "Bopomofo", "Common"),
        "Noto Sans KR": ("Hangul",),
        "Noto Sans Thai": ("Thai",),
        "Noto Sans Oriya": ("Oriya",),
        "Noto Sans Devanagari": ("Devanagari",),
    }
    init = aqt.AnkiApp.__init__

    def init_with_fonts(self: Any, *args: Any, **kwargs: Any) -> None:
        init(self, *args, **kwargs)
        for name in sorted(os.listdir(FONTS)):
            if QFontDatabase.addApplicationFont(os.path.join(FONTS, name)) < 0:
                logger.warning("font not loaded: %s", name)
        for family, scripts in fallbacks.items():
            for script in scripts:
                QFontDatabase.addApplicationFallbackFontFamily(
                    getattr(QChar.Script, f"Script_{script}"), family
                )

    aqt.AnkiApp.__init__ = init_with_fonts  # type: ignore[method-assign]


def _start_threads_yielding() -> None:
    """Thread.start() waits until the new thread runs. Started beyond the
    worker pool (CMakeLists.txt), the thread needs a new Web Worker, which
    loads only when the main thread yields to the browser: waiting on the
    main thread with Event.wait() never would. Wait there with
    _kioku_web.sleep() instead. Only a fallback: while it yields, Qt's events
    can re-enter Python on the main thread, and a caller holding a lock they
    want deadlocks (ThreadPoolExecutor.submit() with a pool of 4), so the
    pool covers what the app runs."""
    import threading

    import _kioku_web

    start = threading.Thread.start

    def start_yielding(self: threading.Thread) -> None:
        if threading.current_thread() is not threading.main_thread():
            return start(self)
        started = self._started  # type: ignore[attr-defined]

        def wait(timeout: float | None = None) -> bool:
            while not started.is_set():
                _kioku_web.sleep(1)
            return True

        started.wait = wait
        try:
            start(self)
        finally:
            del started.wait

    threading.Thread.start = start_yielding  # type: ignore[method-assign]


def _frameless_windows() -> None:
    """Qt for WebAssembly draws a desktop frame (title, maximize, close) on
    every top-level window, above the title bar with Back that Kioku's
    windows module gives them as on a phone. Drop it when a window shows.
    Set on the QWindow: QWidget.setWindowFlag() hides the window to apply
    it, which would end a dialog's exec()."""
    import aqt
    from PyQt6.QtCore import QEvent, QObject, Qt
    from PyQt6.QtWidgets import QWidget

    frameless = Qt.WindowType.FramelessWindowHint

    class Watch(QObject):
        def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
            if (
                event is not None
                and event.type() == QEvent.Type.Show
                and isinstance(obj, QWidget)
                and obj.isWindow()
                and (window := obj.windowHandle()) is not None
                and not window.flags() & frameless
            ):
                window.setFlags(window.flags() | frameless)
            return False

    init = aqt.AnkiApp.__init__

    def init_with_watch(self: Any, *args: Any, **kwargs: Any) -> None:
        init(self, *args, **kwargs)
        self.installEventFilter(Watch(self))

    aqt.AnkiApp.__init__ = init_with_watch  # type: ignore[method-assign]


def _fill_screen() -> None:
    """Like on a phone, the main window fills the page, also when the
    browser window is resized. Qt for WebAssembly leaves it at its desktop
    size, Anki restores its saved geometry when a profile opens, and
    WindowMaximized left it taller than the page."""
    import aqt
    from aqt import gui_hooks
    from PyQt6.QtCore import QEvent, QObject, QTimer

    def fit() -> None:
        mw = aqt.mw
        if mw is None or mw.isFullScreen() or (screen := mw.screen()) is None:
            return
        if mw.geometry() != screen.availableGeometry():
            mw.setGeometry(screen.availableGeometry())

    def fit_soon() -> None:
        # Qt may still apply the stored geometry once the window is exposed
        for delay in (0, 300, 1000):
            QTimer.singleShot(delay, fit)

    class Watch(QObject):
        def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
            if event is not None and event.type() in (QEvent.Type.Show, QEvent.Type.Resize):
                fit_soon()
            return False

    def init() -> None:
        aqt.mw.installEventFilter(Watch(aqt.mw))
        fit_soon()
        if (screen := aqt.mw.screen()) is not None:
            screen.availableGeometryChanged.connect(lambda _: fit())

    gui_hooks.main_window_did_init.append(init)
    gui_hooks.profile_did_open.append(fit_soon)


def _ignore_socket_options() -> None:
    """Emscripten's sockets (WebSockets to the relay) support almost no
    socket options and fail with ENOPROTOOPT; urllib3 sets TCP_NODELAY on
    every connection, and ssl asks for SO_TYPE, so requests (add-on
    downloads) failed. Setting options is only a hint here: skip them;
    SO_TYPE is the socket's own type."""
    import errno
    import socket

    setsockopt = socket.socket.setsockopt

    def quiet_setsockopt(self: socket.socket, *args: Any) -> None:
        try:
            setsockopt(self, *args)
        except OSError as e:
            if e.errno != errno.ENOPROTOOPT:
                raise

    getsockopt = socket.socket.getsockopt

    def known_getsockopt(self: socket.socket, level: int, option: int, *args: Any) -> Any:
        try:
            return getsockopt(self, level, option, *args)
        except OSError as e:
            if e.errno == errno.ENOPROTOOPT and (level, option, args) == (
                socket.SOL_SOCKET,
                socket.SO_TYPE,
                (),
            ):
                return int(self.type)
            raise

    socket.socket.setsockopt = quiet_setsockopt  # type: ignore[method-assign]
    socket.socket.getsockopt = known_getsockopt  # type: ignore[method-assign]


def _save_after_changes() -> None:
    """Save the files to IndexedDB (shell/storage.js) after collection
    changes, besides the page's timer."""
    from aqt import gui_hooks

    gui_hooks.operation_did_execute.append(lambda *_: web.js("persist"))
    gui_hooks.profile_will_close.append(lambda: web.js("persist"))


def _follow_theme() -> None:
    """Tell the page Anki's theme (Preferences > Theme can differ from the
    system's), so the page around the app and iOS's status bar match it."""
    from aqt import gui_hooks
    from aqt.theme import theme_manager

    def tell() -> None:
        web.js("theme", theme_manager.night_mode)

    gui_hooks.main_window_did_init.append(tell)
    gui_hooks.theme_did_change.append(tell)


def _devexec(event: dict) -> None:
    """Development: run Python sent from the page's console with
    __kiokuWeb.post({type: "devexec", code: "..."}); `result` is printed."""
    import traceback

    scope: dict[str, Any] = {}
    try:
        exec(event["code"], scope)
        print("devexec:", repr(scope.get("result")))
    except Exception:
        print("devexec failed:", traceback.format_exc())


def dev_allowed() -> bool:
    return True


def documents_dir() -> str:
    return "/home/web_user/Documents"


def config_dir() -> str:
    return "/home/web_user/.config"


def cache_dir() -> str:
    return "/home/web_user/.cache"


def dark_mode() -> bool:
    """The browser's (and so the system's) light or dark setting."""
    return web.js("darkMode") == "1"


def open_folder(path: str) -> None:
    logger.info("open_folder(%s): not available on the web", path)


def audio_player(taskman: Any, media_folder: str) -> Any:
    from .audio import WebAudioPlayer

    return WebAudioPlayer(taskman, media_folder)


def tts_player(taskman: Any) -> Any:
    from .audio import WebSpeechPlayer

    return WebSpeechPlayer()


def keep_awake() -> None:
    pass


def safe_mode_requested() -> bool:
    """?safe=1 in the page's address (kioku/safemode.py)."""
    from . import web

    return web.js("safeModeRequested") == "1"


def move_to_back() -> None:
    pass


def all_files_access() -> bool:
    return True


def request_all_files_access() -> None:
    pass


def app_versions(packages: list[str]) -> dict[str, str]:
    return {}


def open_app_details(package: str) -> None:
    pass


def launch_ankidroid() -> None:
    pass


def watch_background(on_background: Callable[[], None], on_foreground: Callable[[], None]) -> None:
    pass


def sync_server_running(running: bool, text: str) -> None:
    pass


def screenshot(path: str) -> str:
    return ""
