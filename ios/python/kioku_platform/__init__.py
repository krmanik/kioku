"""iOS platform layer for the shared kioku package: WKWebView, AVFoundation
audio and UIKit helpers, all through rubicon-objc."""

from __future__ import annotations

import logging
import os
from typing import Any

from rubicon.objc import Block, ObjCClass, at
from rubicon.objc.runtime import objc_id

from .files import pick_files, save_path
from .webview import WebView, delete_cookies, prop, set_cookie

__all__ = [
    "WebView",
    "prepare",
    "ankiweb_sync_running",
    "audio_player",
    "cache_dir",
    "config_dir",
    "dark_mode",
    "delete_cookies",
    "dev_allowed",
    "documents_dir",
    "install_done_bar",
    "install_menu_bar",
    "keep_awake",
    "keep_running_in_background",
    "keep_running_in_background_status",
    "key_window",
    "open_folder",
    "pick_files",
    "save_path",
    "screenshot",
    "set_cookie",
    "sync_server_running",
    "tts_player",
    "watch_gamepads",
]

HOME = os.path.expanduser("~")


def prepare() -> None:
    """Runs before Anki is imported.

    HTTPS: Python's OpenSSL has no certificate store on iOS, and truststore
    (which Anki injects) only uses the system trust store when
    platform.system() is "Darwin". Its macOS backend (Security.framework's
    SecTrust) works unchanged on iOS, so load it while platform reports
    macOS.
    """
    import platform

    system, mac_ver = platform.system, platform.mac_ver
    platform.system = lambda: "Darwin"  # type: ignore[assignment]
    platform.mac_ver = lambda *args: ("15.0", ("", "", ""), "arm64")  # type: ignore[assignment]
    try:
        import truststore._api  # noqa: F401
    finally:
        platform.system, platform.mac_ver = system, mac_ver

    try:
        # before add-ons load: only Kioku's own location manager works
        from .location import install_guard

        install_guard()
    except Exception:
        logging.getLogger("kioku").exception("location guard")

    try:
        from .keys import disable_undo_gestures

        disable_undo_gestures()
    except Exception:
        logging.getLogger("kioku").exception("undo gestures")


def dev_allowed() -> bool:
    """The dev command channel runs code from Documents, which the Files app
    shows; only a development build (tools/run_device.sh, run_sim.sh) accepts
    the Documents/.kioku-dev file. KIOKU_DEV in the environment is set only by
    whoever launches the app, so it needs no marker."""
    if os.environ.get("KIOKU_DEV"):
        return True
    # <app>/app/kioku_platform/__init__.py, tools/bundle_python.sh
    app = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.exists(os.path.join(app, "dev-build"))


def documents_dir() -> str:
    # visible in the Files app (UIFileSharingEnabled)
    return os.path.join(HOME, "Documents")


def config_dir() -> str:
    return os.path.join(HOME, "Library")


def cache_dir() -> str:
    return os.path.join(HOME, "Library", "Caches")


def exclude_from_backup(path: str) -> None:
    """Files Kioku can download again (kioku.packs) stay out of backups."""
    url = ObjCClass("NSURL").fileURLWithPath_(path)
    url.setResourceValue_forKey_error_(
        ObjCClass("NSNumber").numberWithBool_(True), at("NSURLIsExcludedFromBackupKey"), None
    )


def dark_mode() -> bool:
    screen = prop(ObjCClass("UIScreen"), "mainScreen")
    traits = prop(screen, "traitCollection")
    return int(prop(traits, "userInterfaceStyle")) == 2  # UIUserInterfaceStyleDark


def open_folder(path: str) -> None:
    # the Files app opens a folder of this app's Documents with this scheme
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices

    QDesktopServices.openUrl(QUrl("shareddocuments://" + QUrl.fromLocalFile(path).path()))


def audio_player(taskman: Any, media_folder: str) -> Any:
    from .audio import AVFoundationPlayer

    return AVFoundationPlayer(taskman, media_folder)


def tts_player(taskman: Any) -> Any:
    from .tts import AVSpeechPlayer

    return AVSpeechPlayer()


def _app() -> Any:
    return prop(ObjCClass("UIApplication"), "sharedApplication")


def install_done_bar(app: Any) -> None:
    """A Done bar above the iPhone's number pad (donebar.py)."""
    from .donebar import install

    install(app)


def install_menu_bar(mw: Any) -> bool:
    """Anki's menus in the iPadOS menu bar (menubar.py); False where there
    is none."""
    from .menubar import install

    return install(mw)


def watch_gamepads(listener: Any) -> None:
    """Game controllers' buttons and sticks to kioku.gamepad's listener;
    None stops."""
    from .gamepad import watch

    watch(listener)


def keep_awake() -> None:
    _app().setIdleTimerDisabled_(True)


def keep_running_in_background(on: bool) -> None:
    """For add-ons that serve other apps (AnkiConnect): location updates
    keep Kioku running after it leaves the foreground (.location)."""
    from .location import keep_running

    keep_running(on)


def keep_running_in_background_status() -> str:
    """"off", "allowed", "asking", "denied" or "on" (.location.status)."""
    from .location import status

    return status()


def key_window() -> Any:
    window = None
    for scene in prop(prop(_app(), "connectedScenes"), "allObjects"):
        for w in prop(scene, "windows"):
            if window is None or prop(w, "isKeyWindow"):
                window = w
    if window is None:
        raise RuntimeError("no window")
    return window


_UIBackgroundTaskInvalid = 0
_sync_task = [_UIBackgroundTaskInvalid]
_sync_task_expired: list[Any] = []  # keeps the expiration block alive
_idle_timer_before: list[bool] = []


def ankiweb_sync_running(running: bool, title: str = "") -> None:
    """While a sync with AnkiWeb (or kioku.packs' download) runs: a
    background task gives it time after Kioku leaves the foreground (iOS
    suspends an app about 5 s after that otherwise, and decides how long
    the task may run), and the screen does not lock while Kioku is open.
    kioku.ankiwebsync resumes a media sync that still got cut off."""
    app = _app()
    log = logging.getLogger("kioku.ankiwebsync")
    if running:
        if not _idle_timer_before:
            _idle_timer_before.append(bool(prop(app, "isIdleTimerDisabled")))
            app.setIdleTimerDisabled_(True)
        if _sync_task[0] == _UIBackgroundTaskInvalid:

            def expired() -> None:
                # iOS kills an app whose task outlives its time: end it
                log.warning("background time for the sync ran out")
                _end_sync_task()

            block = Block(expired, None)
            _sync_task_expired[:] = [block]
            _sync_task[0] = int(
                app.beginBackgroundTaskWithName_expirationHandler_(at("Kioku sync"), block)
            )
            log.info("background task %s started", _sync_task[0])
    else:
        _end_sync_task()
        if _idle_timer_before:
            app.setIdleTimerDisabled_(_idle_timer_before.pop())


def _end_sync_task() -> None:
    task = _sync_task[0]
    if task != _UIBackgroundTaskInvalid:
        _sync_task[0] = _UIBackgroundTaskInvalid
        _app().endBackgroundTask_(task)
        logging.getLogger("kioku.ankiwebsync").info("background task %s ended", task)


def sync_server_running(running: bool, text: str) -> None:
    # iOS has no way to keep serving in the background
    pass


def screenshot(path: str) -> str:
    """Render the key window, native web views included, to a PNG."""
    window = key_window()
    bounds = prop(window, "bounds")
    renderer = ObjCClass("UIGraphicsImageRenderer").alloc().initWithBounds_(bounds)

    def draw(context):  # type: ignore[no-untyped-def]
        window.drawViewHierarchyInRect_afterScreenUpdates_(bounds, True)

    data = renderer.PNGDataWithActions_(Block(draw, None, objc_id))
    data.writeToFile_atomically_(at(path), True)
    return path
