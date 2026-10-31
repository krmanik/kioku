"""Android platform layer for the shared kioku package: android.webkit
web views, MediaPlayer audio and the system file picker, all provided by
KiokuBridge.java."""

from __future__ import annotations

import os
from typing import Any, Callable

from .files import pick_files, save_path
from .webview import WebView, delete_cookies, set_cookie

__all__ = [
    "WebView",
    "all_files_access",
    "app_versions",
    "audio_player",
    "cache_dir",
    "config_dir",
    "dark_mode",
    "delete_cookies",
    "dev_allowed",
    "documents_dir",
    "keep_awake",
    "launch_ankidroid",
    "move_to_back",
    "open_app_details",
    "open_folder",
    "pick_files",
    "prepare",
    "request_all_files_access",
    "save_path",
    "screenshot",
    "set_cookie",
    "sync_server_running",
    "tts_player",
]

HOME = os.path.expanduser("~")


# the system CA certificates; the APEX copy is updated with Conscrypt
# (Android 14+), the /system one is the fallback
CA_DIRS = ("/apex/com.android.conscrypt/cacerts", "/system/etc/security/cacerts")


def prepare() -> None:
    """Runs before Anki is imported."""
    _ca_bundle()
    # Qt turns QMenuBar into the activity's options menu, which has no
    # button without an action bar; draw Anki's menu bar as a widget instead
    from PyQt6.QtCore import QCoreApplication, Qt

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar)


def _ca_bundle() -> None:
    """HTTPS: Python's OpenSSL has no certificate store configured on
    Android, and the system's folder cannot serve as SSL_CERT_DIR: its files
    are named with OpenSSL's old (MD5) subject hash, while OpenSSL 3 looks
    certificates up by the current one. Concatenate them into a bundle
    (truststore, which Anki uses, then picks it up through SSL_CERT_FILE).
    Not in the cache folder: Android empties it when storage runs low, and
    every HTTPS request failed from then on."""
    if "SSL_CERT_FILE" in os.environ:
        return
    folder = next((d for d in CA_DIRS if os.path.isdir(d)), None)
    if folder is None:
        return
    names = sorted(os.listdir(folder))
    bundle = os.path.join(config_dir(), "cacerts.pem")
    stamp = f"{folder} {len(names)} {os.stat(folder).st_mtime_ns}\n"
    try:
        with open(bundle, encoding="ascii", errors="replace") as f:
            current = f.readline() == "# " + stamp
    except OSError:
        current = False
    if not current:
        os.makedirs(config_dir(), exist_ok=True)
        with open(bundle + ".tmp", "w", encoding="ascii", errors="replace") as out:
            out.write("# " + stamp)
            for name in names:
                with open(os.path.join(folder, name), encoding="ascii", errors="replace") as f:
                    out.write(f.read() + "\n")
        os.replace(bundle + ".tmp", bundle)
    os.environ["SSL_CERT_FILE"] = bundle


def dev_allowed() -> bool:
    """The dev command channel runs code from the external files folder,
    which other apps can write on Android 9/10; only development builds
    (tools/run_device.sh) allow it."""
    home = os.environ.get("KIOKU_PYTHON_HOME", "")
    return bool(home) and os.path.exists(os.path.join(home, "dev-build"))


def documents_dir() -> str:
    # the app's external files folder: reachable over USB and by file managers
    return os.environ.get("KIOKU_DOCUMENTS") or os.path.join(HOME, "Documents")


def config_dir() -> str:
    return os.path.join(HOME, ".config")


def cache_dir() -> str:
    return os.environ.get("TMPDIR") or os.path.join(HOME, ".cache")


def dark_mode() -> bool:
    from . import bridge

    return bool(bridge.call("darkMode"))


def open_folder(path: str) -> None:
    # Android has no folder viewer for app-private folders; nothing to open
    from aqt.utils import tooltip

    tooltip(path)


def audio_player(taskman: Any, media_folder: str) -> Any:
    from .audio import MediaPlayerPlayer

    return MediaPlayerPlayer(taskman, media_folder)


def tts_player(taskman: Any) -> Any:
    from .tts import TextToSpeechPlayer

    return TextToSpeechPlayer()


def keep_awake() -> None:
    from . import bridge

    bridge.call("keepAwake")


def move_to_back() -> None:
    from . import bridge

    bridge.call("moveTaskToBack")


def all_files_access() -> bool:
    from . import bridge

    return bool(bridge.call("storage.allFiles"))


def request_all_files_access() -> None:
    """Opens Android's All files access screen for Kioku (Android 9/10: the
    storage permission prompt)."""
    from . import bridge

    bridge.call("storage.requestAllFiles")


def app_versions(packages: list[str]) -> dict[str, str]:
    """{package: versionName} of the installed ones."""
    from . import bridge

    return dict(bridge.call("apps.versions", packages=list(packages)))


def open_app_details(package: str) -> None:
    from . import bridge

    bridge.call("apps.details", package=package)


def launch_ankidroid() -> None:
    from kioku.ankidroid import PACKAGES

    from . import bridge

    installed = app_versions(list(PACKAGES))
    if not installed:
        raise RuntimeError("AnkiDroid isn't installed")
    bridge.call("apps.launch", package=next(p for p in PACKAGES if p in installed))


def watch_background(
    on_background: Callable[[str], str] | None, on_foreground: Callable[[int], None] | None
) -> None:
    """While set, Kioku's activity waits in onPause and onStop (Android's UI
    thread, briefly) for on_background("pause" or "stop") to return
    "closed", "none", "busy" or "wait" (the last two are asked again
    until time runs out), and on_foreground(ms away) runs on resume before
    any other event. None stops it."""
    from . import bridge

    if on_background is None or on_foreground is None:
        bridge.call("lifecycle.watch", on=False)
        return
    bridge.answer("background", lambda request: on_background(request["state"]))
    _foreground[:] = [on_foreground]
    if not _foreground_listening:
        _foreground_listening.append(True)
        bridge.listen(
            "foreground", lambda event: [f(int(event.get("away_ms", 0))) for f in _foreground]
        )
    bridge.call("lifecycle.watch", on=True)


_foreground: list[Callable[[int], None]] = []
_foreground_listening: list[bool] = []


def sync_server_running(running: bool, text: str) -> None:
    """A foreground service (with its notification) keeps the process, and
    with it the sync server, alive while Kioku is in the background."""
    from . import bridge

    if not _sync_stop_listening:
        _sync_stop_listening.append(True)
        bridge.listen("syncServiceStop", _on_sync_stop)
    bridge.call("syncService", running=running, text=text)


_sync_stop_listening: list[bool] = []


def ankiweb_sync_running(running: bool, title: str = "") -> None:
    """A foreground service keeps the network of a sync with AnkiWeb (or of
    other work: title for its notification) while Kioku is in the background."""
    from . import bridge

    bridge.call("ankiWebService", running=running, title=title)


def _on_sync_stop(event: dict) -> None:
    # the notification's Stop: for this run only, the setting stays on
    import threading

    from kioku import syncserver

    threading.Thread(target=syncserver.stop, name="syncserver-stop", daemon=True).start()


def screenshot(path: str) -> str:
    """The Qt surface and the web views are separate Android surfaces; take
    screenshots from the computer instead (adb exec-out screencap -p)."""
    raise NotImplementedError("use android/tools/devcmd.sh --shot")
