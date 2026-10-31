"""iOS platform layer for the shared kioku package: WKWebView, AVFoundation
audio and UIKit helpers, all through rubicon-objc."""

from __future__ import annotations

import os
from typing import Any

from rubicon.objc import Block, ObjCClass, at
from rubicon.objc.runtime import objc_id

from .files import pick_files, save_path
from .webview import WebView, delete_cookies, prop, set_cookie

__all__ = [
    "WebView",
    "prepare",
    "audio_player",
    "cache_dir",
    "config_dir",
    "dark_mode",
    "delete_cookies",
    "documents_dir",
    "keep_awake",
    "key_window",
    "open_folder",
    "pick_files",
    "save_path",
    "screenshot",
    "set_cookie",
    "sync_server_running",
    "tts_player",
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


def keep_awake() -> None:
    _app().setIdleTimerDisabled_(True)


def key_window() -> Any:
    window = None
    for scene in prop(prop(_app(), "connectedScenes"), "allObjects"):
        for w in prop(scene, "windows"):
            if window is None or prop(w, "isKeyWindow"):
                window = w
    if window is None:
        raise RuntimeError("no window")
    return window


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
