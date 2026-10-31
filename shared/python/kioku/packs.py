"""Extra files for add-ons ("packs"): data and pure-Python packages that only
some add-ons use, downloaded when one needs them instead of making every
download of the app larger. Native code can't be downloaded on iOS, so packs
hold files only: jieba, Tesseract's languages, eSpeak NG's voices.

packs.json lists them. shared/tools/packs.py leaves their files out of the
app bundles, builds the zips and publishes them on the repository's packs
branch. A pack unpacks to <config>/kioku-packs/<id>/, laid out like
site-packages: that folder is on sys.path (Python packages) and the pack's
env variables point into it (program data), so a pack works as soon as it
has been downloaded.

Kioku offers to download a pack
  - after an add-on that needs it is installed, and when a profile opens
    for the installed ones (needs(): imports and program names in any
    add-on's code, no list of add-ons);
  - when an add-on imports one of its modules or starts one of its programs.
Tools › Add-ons › Extra Files… downloads, updates and removes them. A build
that still includes a pack's files shows it as included."""

from __future__ import annotations

import fnmatch
import glob
import hashlib
import importlib
import json
import os
import re
import shutil
import sys
import threading
import zipfile
from dataclasses import dataclass
from typing import Any, Callable

INFO_FILE = ".kioku-pack.json"
STATE_FILE = "state.json"
# bump when _scan() changes, so cached results are made again
SCAN_VERSION = 1
# larger .py files are generated tables (jieba's own), not code to search
SCAN_LIMIT = 2 << 20


@dataclass
class Pack:
    id: str
    title: str
    description: str
    version: str
    site: tuple[str, ...]
    drop: tuple[str, ...]
    modules: tuple[str, ...]
    imports: tuple[str, ...]
    programs: tuple[str, ...]
    env: dict[str, str]
    own_files: tuple[str, ...]
    size: int
    unpacked: int
    sha256: str

    @property
    def file(self) -> str:
        return f"{self.id}-{self.version}.zip"


def _load() -> tuple[str, list[Pack]]:
    with open(os.path.join(os.path.dirname(__file__), "packs.json"), encoding="utf-8") as f:
        data = json.load(f)
    packs = []
    for entry in data["packs"]:
        fields = {k: tuple(v) if isinstance(v, list) else v for k, v in entry.items()}
        packs.append(Pack(**fields))
    return data["base_url"], packs


BASE_URL, PACKS = _load()

_lock = threading.RLock()
_site: list[str] = []
_bundled: dict[str, bool] = {}
_state_cache: dict[str, Any] | None = None
# pack id -> add-on folders waiting for an offer
_pending: dict[str, set[str]] = {}
_asked: set[str] = set()
# imported or started before the pack was there: a restart may be needed
_failed: set[str] = set()
# pack id -> [bytes received, bytes expected]
_downloads: dict[str, list[int]] = {}
_listeners: list[Callable[[], None]] = []
_ready = False
_offering = False


def get(pack_id: str) -> Pack | None:
    return next((p for p in PACKS if p.id == pack_id), None)


def root() -> str:
    path = os.environ.get("KIOKU_PACKS_DIR")
    if not path:
        import kioku_platform as platform

        path = os.path.join(platform.config_dir(), "kioku-packs")
    return path


def base_url() -> str:
    return os.environ.get("KIOKU_PACKS_URL") or BASE_URL


def pack_dir(pack: Pack) -> str:
    return os.path.join(root(), pack.id)


# what is on the device


def bundled(pack: Pack) -> bool:
    """The app (an older build, or one made with the files) has them."""
    if pack.id not in _bundled:
        paths = _site or [p for p in sys.path if os.path.isdir(p) and not p.startswith(root())]
        _bundled[pack.id] = all(any(glob.glob(os.path.join(d, rel)) for d in paths) for rel in pack.site)
    return _bundled[pack.id]


def _info(pack: Pack) -> dict[str, Any]:
    try:
        with open(os.path.join(pack_dir(pack), INFO_FILE), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def installed_version(pack: Pack) -> str | None:
    return _info(pack).get("version")


def available(pack: Pack) -> bool:
    return bundled(pack) or installed_version(pack) is not None


def outdated(pack: Pack) -> bool:
    version = installed_version(pack)
    return not bundled(pack) and version is not None and version != pack.version


def disk_size(pack: Pack) -> int:
    return int(_info(pack).get("unpacked") or 0)


def status(pack: Pack) -> str:
    """bundled, downloading, missing, outdated or installed"""
    if bundled(pack):
        return "bundled"
    if pack.id in _downloads:
        return "downloading"
    if installed_version(pack) is None:
        return "missing"
    return "outdated" if outdated(pack) else "installed"


def progress(pack: Pack) -> float:
    got, total = _downloads.get(pack.id, (0, 0))
    return min(got / total, 1.0) if total else 0.0


# start-up


def setup() -> None:
    """Before add-ons load: put the packs' folders on sys.path and point
    their variables into them, whether downloaded yet or not."""
    global _site
    _site = [p for p in sys.path if os.path.isdir(p)]
    _bundled.clear()
    for pack in PACKS:
        if bundled(pack):
            continue
        folder = pack_dir(pack)
        if pack.modules and folder not in sys.path:
            sys.path.append(folder)
        for name, rel in pack.env.items():
            os.environ.setdefault(name, os.path.join(folder, rel))
    if not any(isinstance(f, _Finder) for f in sys.meta_path):
        sys.meta_path.append(_Finder())


class _Finder:
    """Last on sys.meta_path, so it only sees imports nothing else found.
    Only add-ons' imports count: libraries probe optional modules (markdown
    tries pygments) and do without them."""

    def find_spec(self, name, path=None, target=None):  # type: ignore[no-untyped-def]
        if path is None:
            for pack in PACKS:
                if name in pack.modules and not available(pack):
                    addon = _caller_addon()
                    if addon:
                        wanted(pack, addon)
        return None

    def invalidate_caches(self) -> None:
        pass


def program_started(name: str) -> None:
    """kioku.programs: an add-on starts one of the bundled programs."""
    for pack in PACKS:
        if name in pack.programs and not available(pack):
            addon = _caller_addon()
            if addon:
                wanted(pack, addon)


_ADDON_PATH = re.compile(r"[/\\]addons21[/\\]([^/\\]+)")


def _caller_addon() -> str | None:
    frame = sys._getframe(1)
    while frame is not None:
        match = _ADDON_PATH.search(frame.f_code.co_filename)
        if match:
            return match.group(1)
        frame = frame.f_back
    return None


# which add-on needs what


def needs(folder: str) -> list[Pack]:
    """The packs the add-on in folder (addons21/<dir>) uses."""
    dir_name = os.path.basename(folder.rstrip("/\\"))
    try:
        stamp = max(os.stat(folder).st_mtime_ns, os.stat(os.path.join(folder, "__init__.py")).st_mtime_ns)
    except OSError:
        return []
    with _lock:
        cache = _state().setdefault("scan", {})
        hit = cache.get(dir_name)
    if hit and hit[0] == stamp and hit[1] == SCAN_VERSION:
        ids = hit[2]
    else:
        ids = _scan(folder, dir_name)
        with _lock:
            cache[dir_name] = [stamp, SCAN_VERSION, ids]
            _save_state()
    return [p for p in PACKS if p.id in ids]


def _scan(folder: str, dir_name: str) -> list[str]:
    found: set[str] = set()
    dirs: set[str] = set()
    files: set[str] = set()
    code = []
    for base, subdirs, names in os.walk(folder):
        subdirs[:] = [d for d in subdirs if d not in ("__pycache__", "user_files")]
        dirs.update(subdirs)
        files.update(names)
        for name in names:
            path = os.path.join(base, name)
            try:
                if name.endswith(".py") and os.path.getsize(path) <= SCAN_LIMIT:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        code.append(f.read())
            except OSError:
                pass
    text = "\n".join(code)
    for pack in PACKS:
        if pack.id in found:
            continue
        # its own copy: a vendored package or its own data files
        if any(m in dirs or f"{m}.py" in files for m in pack.modules):
            continue
        if any(fnmatch.filter(files, pattern) for pattern in pack.own_files):
            continue
        imports = pack.modules + pack.imports
        if imports and re.search(
            rf"^\s*(?:import|from)\s+(?:{'|'.join(map(re.escape, imports))})\b", text, re.M
        ):
            found.add(pack.id)
        elif pack.programs and re.search(
            rf"""["'/\\](?:{'|'.join(map(re.escape, pack.programs))})(?:\.exe|\.lin|\.mac)?["']""", text
        ):
            found.add(pack.id)
    return sorted(found)


# state: packs declined, scan results


def _state() -> dict[str, Any]:
    global _state_cache
    with _lock:
        if _state_cache is None:
            try:
                with open(os.path.join(root(), STATE_FILE), encoding="utf-8") as f:
                    _state_cache = json.load(f)
            except (OSError, ValueError):
                _state_cache = {}
        return _state_cache


def _save_state() -> None:
    with _lock:
        try:
            os.makedirs(root(), exist_ok=True)
            path = os.path.join(root(), STATE_FILE)
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(_state(), f)
            os.replace(path + ".tmp", path)
        except OSError:
            pass


def _declined(pack: Pack) -> bool:
    return pack.id in _state().get("declined", [])


def _set_declined(packs: list[Pack], declined: bool) -> None:
    with _lock:
        ids = set(_state().get("declined", []))
        ids = ids | {p.id for p in packs} if declined else ids - {p.id for p in packs}
        _state()["declined"] = sorted(ids)
        _save_state()


# offers


def wanted(pack: Pack, addon: str | None = None, *, force: bool = False, failed: bool = True) -> None:
    """Offer the pack when a profile is open. force: even if offered or
    declined before (an add-on was just installed)."""
    if pack.id in _downloads or (available(pack) and not outdated(pack)):
        return
    with _lock:
        if failed and not available(pack):
            _failed.add(pack.id)
        if not force and (pack.id in _asked or _declined(pack)):
            return
        _pending.setdefault(pack.id, set())
        if addon:
            _pending[pack.id].add(addon)
        ready = _ready
    if ready:
        _schedule()


def _schedule(delay: int = 500) -> None:
    import aqt
    from aqt.qt import QTimer

    if aqt.mw is not None:
        aqt.mw.taskman.run_on_main(lambda: QTimer.singleShot(delay, _offer))


def _addon_name(dir_name: str) -> str:
    import aqt

    try:
        return aqt.mw.addonManager.addonName(dir_name)
    except Exception:
        return dir_name


def _offer() -> None:
    global _offering
    if _offering:
        return
    with _lock:
        pending = dict(_pending)
        _pending.clear()
    packs = [p for p in PACKS if p.id in pending and p.id not in _downloads and status(p) in ("missing", "outdated")]
    if not packs:
        return
    _asked.update(p.id for p in packs)
    names = sorted({_addon_name(a) for p in packs for a in pending[p.id]})
    items = "\n".join(f"• {p.title} ({human_size(p.size)})" for p in packs)
    if all(status(p) == "outdated" for p in packs):
        text = f"New versions of extra files for add-ons are available:\n\n{items}\n\nDownload them now?"
    else:
        who = ", ".join(names) or "An add-on"
        verb = "need" if len(names) > 1 else "needs"
        text = (
            f"{who} {verb} extra files that Kioku doesn't include, to keep the app small:\n\n"
            f"{items}\n\nDownload them now? You can keep using Kioku while they download."
        )

    def answer(index: int) -> None:
        global _offering
        _offering = False
        if index == 0:
            for pack in packs:
                download(pack)
        else:
            _set_declined(packs, True)
        if _pending:
            _schedule()

    from aqt.utils import ask_user_dialog

    _offering = True
    try:
        ask_user_dialog(text, answer, buttons=["Download", "Not now"], default_button=0, parent=_parent())
    except Exception:
        _offering = False
        raise


def _parent():  # type: ignore[no-untyped-def]
    import aqt

    return aqt.mw.app.activeWindow() or aqt.mw


def _on_profile_open() -> None:
    """Offer what installed add-ons need (once, unless declined) and new
    versions of downloaded packs."""
    global _ready
    import aqt

    mw = aqt.mw

    def scan() -> list[tuple[Pack, str | None]]:
        found: list[tuple[Pack, str | None]] = [(p, None) for p in PACKS if outdated(p)]
        for meta in mw.addonManager.all_addon_meta():
            if meta.enabled:
                for pack in needs(mw.addonManager.addonsFolder(meta.dir_name)):
                    if not available(pack):
                        found.append((pack, meta.dir_name))
        return found

    def done(fut) -> None:  # type: ignore[no-untyped-def]
        global _ready
        try:
            for pack, addon in fut.result():
                wanted(pack, addon, failed=False)
        except Exception as e:
            print(f"Kioku: extra files scan failed: {e}")
        with _lock:
            _ready = True
        _schedule(1500)

    mw.taskman.run_in_background(scan, done, uses_collection=False)


def _on_addon_installed(manager, dir_name: str) -> None:  # type: ignore[no-untyped-def]
    for pack in needs(manager.addonsFolder(dir_name)):
        if not available(pack):
            wanted(pack, dir_name, force=True, failed=False)


# download, install, remove


def download(pack: Pack) -> None:
    """In the background; listeners hear about progress and the end."""
    import aqt
    from aqt.utils import showWarning, tooltip

    if pack.id in _downloads:
        return
    if _declined(pack):
        _set_declined([pack], False)
    _downloads[pack.id] = [0, pack.size]
    _keep_network(True)
    _notify()

    def on_progress(got: int) -> None:
        _downloads[pack.id][0] = got

    def done(fut) -> None:  # type: ignore[no-untyped-def]
        _downloads.pop(pack.id, None)
        _keep_network(bool(_downloads))
        try:
            fut.result()
        except Exception as e:
            showWarning(
                f"Couldn't download {pack.title}:\n{e}\n\n"
                "Try again in Tools › Add-ons › Extra Files.",
                parent=_parent(),
            )
        else:
            message = f"Downloaded {pack.title}."
            if pack.id in _failed and pack.modules:
                message += " Restart Kioku if an add-on still can't find it."
            tooltip(message, parent=_parent())
        _notify()

    aqt.mw.taskman.run_in_background(lambda: fetch(pack, on_progress), done, uses_collection=False)


def fetch(pack: Pack, on_progress: Callable[[int], None] | None = None) -> None:
    from anki.httpclient import HttpClient

    os.makedirs(root(), exist_ok=True)
    part = os.path.join(root(), f".{pack.file}.part")
    digest = hashlib.sha256()
    got = 0
    try:
        with HttpClient() as client:
            client.timeout = 30
            resp = client.get(base_url() + pack.file)
            resp.raise_for_status()
            with open(part, "wb") as out:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    out.write(chunk)
                    digest.update(chunk)
                    got += len(chunk)
                    if on_progress:
                        on_progress(got)
        if pack.sha256 and digest.hexdigest() != pack.sha256:
            raise ValueError("the download is damaged (checksum mismatch)")
        install_file(pack, part)
    finally:
        if os.path.exists(part):
            os.remove(part)


def install_file(pack: Pack, path: str) -> None:
    """Unpack a pack's zip into its folder, replacing an older version."""
    folder = pack_dir(pack)
    new, old = folder + ".new", folder + ".old"
    for d in (new, old):
        shutil.rmtree(d, ignore_errors=True)
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            norm = os.path.normpath(name)
            if os.path.isabs(norm) or norm == ".." or norm.startswith(".." + os.sep):
                raise ValueError(f"unexpected path in the download: {name}")
        z.extractall(new)
        unpacked = sum(i.file_size for i in z.infolist())
    with open(os.path.join(new, INFO_FILE), "w", encoding="utf-8") as f:
        json.dump({"version": pack.version, "sha256": pack.sha256, "unpacked": unpacked}, f)
    if os.path.exists(folder):
        os.rename(folder, old)
    os.rename(new, folder)
    shutil.rmtree(old, ignore_errors=True)
    _exclude_from_backup(root())
    importlib.invalidate_caches()


def remove(pack: Pack) -> None:
    if bundled(pack):
        return
    shutil.rmtree(pack_dir(pack), ignore_errors=True)
    importlib.invalidate_caches()
    _notify()


def _exclude_from_backup(path: str) -> None:
    """iOS: downloadable files stay out of iCloud backups."""
    try:
        import kioku_platform as platform

        exclude = getattr(platform, "exclude_from_backup", None)
        if exclude:
            exclude(path)
    except Exception:
        pass


def _keep_network(on: bool) -> None:
    """Android cuts the network of apps in the background."""
    if sys.platform == "android":
        from kioku import ankiwebsync

        ankiwebsync.hold("packs", on)


def add_listener(listener: Callable[[], None]) -> None:
    _listeners.append(listener)


def remove_listener(listener: Callable[[], None]) -> None:
    if listener in _listeners:
        _listeners.remove(listener)


def _notify() -> None:
    for listener in list(_listeners):
        try:
            listener()
        except Exception:
            pass


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("bytes", "KB", "MB"):
        if value < 1000:
            return f"{value:.0f} {unit}" if unit == "bytes" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{value:.1f} GB"


# Tools › Add-ons


def install() -> None:
    from aqt import gui_hooks

    gui_hooks.profile_did_open.append(_on_profile_open)
    gui_hooks.addon_manager_did_install_addon.append(_on_addon_installed)
    gui_hooks.addons_dialog_will_show.append(_on_addons_dialog)


def _on_addons_dialog(dialog) -> None:  # type: ignore[no-untyped-def]
    from aqt.qt import QPushButton, qconnect

    form = dialog.form
    button = QPushButton("Extra Files…", dialog)
    layout = getattr(form, "verticalLayout", None)
    anchor = getattr(form, "viewFiles", None)
    if layout is not None and anchor is not None and layout.indexOf(anchor) >= 0:
        layout.insertWidget(layout.indexOf(anchor) + 1, button)
    elif layout is not None:
        layout.addWidget(button)
    else:
        return

    def selected() -> str | None:
        try:
            dirs = dialog.selectedAddons()
        except Exception:
            return None
        return dirs[0] if len(dirs) == 1 else None

    def update_label() -> None:
        dir_name = selected()
        missing = 0
        if dir_name:
            missing = sum(1 for p in needs(dialog.mgr.addonsFolder(dir_name)) if not available(p))
        button.setText(f"Extra Files ({missing} needed)…" if missing else "Extra Files…")

    qconnect(button.clicked, lambda: ExtraFilesDialog(dialog, selected()).open())
    list_widget = getattr(form, "addonList", None)
    if list_widget is not None:
        qconnect(list_widget.itemSelectionChanged, update_label)
    update_label()


def _dialog_class():  # type: ignore[no-untyped-def]
    from aqt.qt import (
        QDialog,
        QDialogButtonBox,
        QFrame,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
        QTimer,
        QVBoxLayout,
        QWidget,
        qconnect,
    )
    from aqt.utils import askUser, tooltip

    class ExtraFilesDialog(QDialog):
        """Download, update or remove packs; the selected add-on's first."""

        def __init__(self, parent, addon: str | None = None) -> None:  # type: ignore[no-untyped-def]
            super().__init__(parent)
            self.setWindowTitle("Extra Files")
            self._rows: list[tuple[Pack, QLabel, QPushButton, QPushButton]] = []
            layout = QVBoxLayout(self)
            intro = QLabel(
                "Files some add-ons need. Kioku downloads them only when you want them, "
                "to keep the app small. Remove them to free space."
            )
            intro.setWordWrap(True)
            layout.addWidget(intro)

            needed: list[Pack] = []
            if addon:
                import aqt

                needed = needs(aqt.mw.addonManager.addonsFolder(addon))
            others = [p for p in PACKS if p not in needed]
            content = QWidget()
            rows = QVBoxLayout(content)
            if addon:
                rows.addWidget(self._heading(
                    f"Needed by {_addon_name(addon)}" if needed else f"{_addon_name(addon)} needs none of these."
                ))
                for pack in needed:
                    rows.addWidget(self._row(pack))
                if others:
                    rows.addWidget(self._heading("Other extra files"))
            for pack in others:
                rows.addWidget(self._row(pack))
            rows.addStretch()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(content)
            layout.addWidget(scroll)

            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            qconnect(buttons.rejected, self.reject)
            layout.addWidget(buttons)

            self._timer = QTimer(self)
            qconnect(self._timer.timeout, self._refresh)
            self._timer.start(500)
            add_listener(self._refresh)
            qconnect(self.finished, lambda _: remove_listener(self._refresh))
            self._refresh()

        def _heading(self, text: str) -> QLabel:
            label = QLabel(f"<b>{text}</b>")
            label.setWordWrap(True)
            return label

        def _row(self, pack: Pack) -> QFrame:
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            box = QVBoxLayout(frame)
            title = QLabel(f"<b>{pack.title}</b>")
            title.setWordWrap(True)
            description = QLabel(pack.description)
            description.setWordWrap(True)
            state = QLabel()
            state.setWordWrap(True)
            get_button = QPushButton("Download")
            remove_button = QPushButton("Remove")
            qconnect(get_button.clicked, lambda: download(pack))
            qconnect(remove_button.clicked, lambda: self._remove(pack))
            line = QHBoxLayout()
            line.addWidget(state, 1)
            line.addWidget(get_button)
            line.addWidget(remove_button)
            for widget in (title, description):
                box.addWidget(widget)
            box.addLayout(line)
            self._rows.append((pack, state, get_button, remove_button))
            return frame

        def _remove(self, pack: Pack) -> None:
            if askUser(
                f"Remove {pack.title}? Add-ons that need it won't work until you download it again.",
                parent=self,
            ):
                remove(pack)
                tooltip(f"Removed {pack.title}.", parent=self)

        def _refresh(self) -> None:
            for pack, state, get_button, remove_button in self._rows:
                now = status(pack)
                get_button.setVisible(now in ("missing", "outdated", "downloading"))
                get_button.setEnabled(now != "downloading")
                get_button.setText("Update" if now == "outdated" else "Download")
                remove_button.setVisible(now in ("installed", "outdated"))
                if now == "bundled":
                    state.setText("Included in the app")
                elif now == "downloading":
                    state.setText(f"Downloading… {progress(pack) * 100:.0f}%")
                elif now == "missing":
                    state.setText(f"Not downloaded · {human_size(pack.size)}")
                elif now == "outdated":
                    state.setText(f"New version · {human_size(pack.size)}")
                else:
                    state.setText(f"Downloaded · {human_size(disk_size(pack))}")

    return ExtraFilesDialog


def ExtraFilesDialog(parent, addon: str | None = None):  # type: ignore[no-untyped-def]
    return _dialog_class()(parent, addon)
