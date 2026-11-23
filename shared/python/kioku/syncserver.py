"""This phone as a sync server (Preferences > Advanced).

Anki's own sync server (the Rust one behind `anki --syncserver`) runs on a
background thread of the app, through syncserver_start()/syncserver_stop(),
which Kioku adds to rsbridge (shared/patches/anki-syncserver.patch). AnkiDroid
on the same phone, Kioku's own profiles and desktop Anki on other machines can
then sync with the phone instead of AnkiWeb.

The server keeps its own copy of each user's collection and media in an
app-private folder; the settings are global (not per profile) and live in
Anki's prefs21.db next to the other global preferences.

On Android a foreground service keeps the process alive while the server runs;
iOS cannot serve in the background and reclaims the listening socket there,
so the server is started again when the app comes back.

Anki builds without that patch (the Termux variant runs Termux's own Anki)
have only upstream's blocking syncserver(): the server then runs in a child
process (_ServerProcess).
"""

from __future__ import annotations

import ipaddress
import logging
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import asdict, dataclass

import kioku_platform as platform

logger = logging.getLogger("kioku.syncserver")

META_KEY = "kioku_syncserver"

LOCAL = "local"
TAILSCALE = "tailscale"
ALL = "all"
LISTEN_CHOICES = (LOCAL, TAILSCALE, ALL)

THIS_PHONE = "This phone (AnkiDroid, Kioku)" if sys.platform == "android" else "This phone"

# Tailscale gives each device an address in 100.64.0.0/10; its DNS server
# 100.100.100.100 is only routed through the Tailscale interface
TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")
TAILSCALE_PROBE = "100.100.100.100"

# Anki's server limits a sync request to MAX_SYNC_PAYLOAD_MEGS (default 100)
# and a collection to 3 times that uncompressed. A collection over 300 MB was
# forced into a full sync on every sync, whose upload the server then refused
# ("collection exceeds size limit", issue #28). Self-hosting is how big
# collections get synced, so the limit is raised to 3 GB. Read once per
# process: start() sets it before the profile's first sync. In-process clients
# use it only to check uploads to AnkiWeb early, which AnkiWeb checks again.
MAX_SYNC_PAYLOAD_MEGS = "1024"


@dataclass
class Settings:
    enabled: bool = False
    listen: str = LOCAL
    port: int = 8080
    username: str = "kioku"
    password: str = ""

    def problem(self) -> str | None:
        """Why the server can't start with these settings, or None."""
        if self.listen not in LISTEN_CHOICES:
            return f"unknown address choice {self.listen!r}"
        if not 1024 <= self.port <= 65535:
            return "The port must be between 1024 and 65535."
        if not self.username or ":" in self.username or "/" in self.username:
            return "The user name can't be empty or contain ':' or '/'."
        if self.username in (".", ".."):
            return "That user name isn't allowed."
        if len(self.password) < 8:
            return "The password needs at least 8 characters."
        return None


def new_password() -> str:
    return secrets.token_urlsafe(9)


def load_settings(meta: dict) -> Settings:
    stored = meta.get(META_KEY) or {}
    settings = Settings()
    for key, value in stored.items():
        if hasattr(settings, key) and isinstance(value, type(getattr(settings, key))):
            setattr(settings, key, value)
    return settings


def save_settings(pm, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    pm.meta[META_KEY] = asdict(settings)
    # the profile list (no profile open) has no pm.save(); write _global alone
    pm.db.execute(
        "update profiles set data = ? where name = ?", pm._pickle(pm.meta), "_global"
    )
    pm.db.commit()


def base_folder() -> str:
    # app-private: the collections of everyone who syncs here
    return os.path.join(platform.config_dir(), "kioku-syncserver")


def user_folder(settings: Settings) -> str:
    return os.path.join(base_folder(), settings.username)


# Addresses
######################################################################


def _route_address(target: str) -> str | None:
    """The phone's own address on the route to `target` (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((target, 9))
            return s.getsockname()[0]
    except OSError:
        return None


def tailscale_address() -> str | None:
    address = _route_address(TAILSCALE_PROBE)
    if address and ipaddress.ip_address(address) in TAILSCALE_NET:
        return address
    return None


def network_address() -> str | None:
    """The address other devices on the Wi-Fi network reach the phone on."""
    address = _route_address("192.0.2.1")
    if address and not ipaddress.ip_address(address).is_loopback:
        return address
    return None


def bind_host(settings: Settings) -> str:
    if settings.listen == LOCAL:
        return "127.0.0.1"
    if settings.listen == TAILSCALE:
        address = tailscale_address()
        if address is None:
            raise ServerError(
                "Tailscale isn't connected, so there is no Tailscale address to listen on."
            )
        return address
    return "0.0.0.0"


def urls(settings: Settings, host: str | None = None) -> list[tuple[str, str]]:
    """(who it is for, URL) pairs for the current settings."""
    port = settings.port
    if settings.listen == LOCAL:
        return [(THIS_PHONE, f"http://127.0.0.1:{port}/")]
    if settings.listen == TAILSCALE:
        address = host or tailscale_address()
        if address is None:
            return []
        return [("This phone and your Tailscale devices", f"http://{address}:{port}/")]
    found = [(THIS_PHONE, f"http://127.0.0.1:{port}/")]
    if address := network_address():
        found.append(("Other devices on this network", f"http://{address}:{port}/"))
    if address := tailscale_address():
        found.append(("Your Tailscale devices", f"http://{address}:{port}/"))
    return found


# Running
######################################################################


class ServerError(Exception):
    pass


@dataclass
class Status:
    running: bool = False
    host: str | None = None
    port: int | None = None
    error: str | None = None


_lock = threading.Lock()
_status = Status()
_running_settings: Settings | None = None


def status() -> Status:
    return Status(**asdict(_status))


def own_url() -> str | None:
    """The URL a profile in this app syncs with the running server by."""
    st = status()
    if not st.running:
        return None
    host = "127.0.0.1" if st.host in ("127.0.0.1", "0.0.0.0") else st.host
    return f"http://{host}:{st.port}/"


def _rsbridge():  # type: ignore[no-untyped-def]
    from anki import _rsbridge

    return _rsbridge


def start(settings: Settings) -> Status:
    """Starts the server (stopping a running one first). Blocks briefly;
    call it off the main thread."""
    global _status, _running_settings
    with _lock:
        try:
            if problem := settings.problem():
                raise ServerError(problem)
            host = bind_host(settings)
            os.makedirs(base_folder(), exist_ok=True)
            # the server reads its users from the environment
            for key in [k for k in os.environ if k.startswith("SYNC_USER")]:
                del os.environ[key]
            os.environ["SYNC_USER1"] = f"{settings.username}:{settings.password}"
            os.environ.setdefault("RUST_LOG", "anki=info")
            os.environ.setdefault("MAX_SYNC_PAYLOAD_MEGS", MAX_SYNC_PAYLOAD_MEGS)
            try:
                bridge = _rsbridge()
                if hasattr(bridge, "syncserver_start"):
                    port = bridge.syncserver_start(host, settings.port, base_folder())
                else:
                    port = _process.start(host, settings.port, base_folder())
            except Exception as err:
                raise ServerError(_explain(str(err), settings)) from err
            finally:
                os.environ.pop("SYNC_USER1", None)
            _status = Status(running=True, host=host, port=port)
            _running_settings = settings
            logger.info("sync server listening on %s:%d", host, port)
        except ServerError as err:
            _status = Status(error=str(err))
            _running_settings = None
            logger.warning("sync server: %s", err)
    _notify_platform()
    return status()


def stop() -> None:
    """Stops the server; waits for syncs in progress (a few seconds at most)."""
    global _status, _running_settings
    with _lock:
        try:
            bridge = _rsbridge()
            if hasattr(bridge, "syncserver_stop"):
                bridge.syncserver_stop()
            else:
                _process.stop()
        except Exception:
            logger.exception("stopping the sync server")
        _status = Status()
        _running_settings = None
    _notify_platform()


class _ServerProcess:
    """Upstream's server (`anki --syncserver`) in a child process. It takes
    its settings from the environment (SYNC_USER1 is set by start()) and
    ends with this process."""

    # how long the child may take to listen, and to stop
    START_SECONDS = 15.0
    STOP_SECONDS = 5.0
    CODE = "from anki._rsbridge import syncserver; syncserver()"

    def __init__(self) -> None:
        self._child: subprocess.Popen | None = None

    def start(self, host: str, port: int, base: str) -> int:
        self.stop()
        env = dict(os.environ, SYNC_HOST=host, SYNC_PORT=str(port), SYNC_BASE=base)
        log_path = os.path.join(base, "server.log")
        with open(log_path, "wb") as log:
            self._child = subprocess.Popen(
                [sys.executable, "-c", self.CODE], env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, preexec_fn=_end_with_parent,
            )
        probe = "127.0.0.1" if host == "0.0.0.0" else host
        deadline = time.monotonic() + self.START_SECONDS
        while time.monotonic() < deadline:
            if self._child.poll() is not None:
                self._child = None
                raise ServerError(_tail(log_path) or "The sync server stopped right away.")
            # the server's answer: something else may listen on the port
            try:
                with urllib.request.urlopen(f"http://{probe}:{port}/health", timeout=0.5):
                    return port
            except OSError:
                time.sleep(0.1)
        self.stop()
        raise ServerError("The sync server didn't start listening.")

    def stop(self) -> None:
        child, self._child = self._child, None
        if child is None or child.poll() is not None:
            return
        child.terminate()
        try:
            child.wait(self.STOP_SECONDS)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def _end_with_parent() -> None:
    # Linux/Android: the child gets SIGTERM when Anki's process ends, so the
    # port isn't left taken
    try:
        import ctypes

        PR_SET_PDEATHSIG = 1
        ctypes.CDLL(None).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
    except Exception:
        pass


def _tail(path: str, lines: int = 5) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return "".join(fh.readlines()[-lines:]).strip()
    except OSError:
        return ""


_process = _ServerProcess()


def _explain(error: str, settings: Settings) -> str:
    if "couldn't bind" in error or "Address already in use" in error or "in use" in error:
        return (
            f"Port {settings.port} is already in use by another app. Choose another port."
        )
    return error


def answers() -> bool:
    """Whether the running server still answers (iOS drops listening sockets
    of apps in the background)."""
    current = _status
    if not current.running or current.port is None:
        return False
    host = "127.0.0.1" if current.host == "0.0.0.0" else current.host
    try:
        with urllib.request.urlopen(f"http://{host}:{current.port}/health", timeout=2):
            return True
    except Exception:
        return False


def _notify_platform() -> None:
    current = _status
    try:
        if current.running:
            platform.sync_server_running(True, f"Listening on port {current.port}")
        else:
            platform.sync_server_running(False, "")
    except Exception:
        logger.exception("telling the platform about the sync server")


# Data
######################################################################


def storage_used() -> int:
    total = 0
    for folder, _dirs, files in os.walk(base_folder()):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(folder, name))
            except OSError:
                pass
    return total


def has_data(settings: Settings) -> bool:
    return os.path.exists(os.path.join(user_folder(settings), "collection.anki2"))


def delete_data() -> None:
    """Deletes every user's synced collection and media. The caller stops
    the server first."""
    folder = base_folder()
    if os.path.isdir(folder):
        shutil.rmtree(folder)


# App integration
######################################################################


def install() -> None:
    """Starts the server with the app when it is turned on, and on iOS again
    after the app was in the background."""
    import aqt
    import aqt.main
    from aqt.qt import QGuiApplication, Qt, QTimer

    original_init = aqt.main.AnkiQt.__init__

    def init(self, app, profileManager, *args, **kwargs):  # type: ignore[no-untyped-def]
        # before the main window opens a profile, whose sync status check or
        # automatic sync may use this server; binding takes milliseconds
        try:
            settings = load_settings(profileManager.meta)
            if settings.enabled:
                start(settings)
        except Exception:
            logger.exception("starting the sync server")
        original_init(self, app, profileManager, *args, **kwargs)

    aqt.main.AnkiQt.__init__ = init

    def check() -> None:
        mw = aqt.mw
        settings = _running_settings
        if mw is None or settings is None:
            return

        def restart_if_dead() -> None:
            if not answers():
                logger.warning("sync server stopped answering; starting it again")
                start(settings)

        mw.taskman.run_in_background(restart_if_dead, uses_collection=False)

    def on_state(state: Qt.ApplicationState) -> None:
        if state == Qt.ApplicationState.ApplicationActive:
            QTimer.singleShot(500, check)

    app = QGuiApplication.instance()
    if app is not None:
        app.applicationStateChanged.connect(on_state)
