"""Extra files for add-ons (kioku.packs): which add-ons need a pack, the
download and its checks, sys.path and variables, offers on import, and the
manifest the apps ship (shared/tools/packs.py build)."""

from __future__ import annotations

import functools
import hashlib
import http.server
import importlib
import os
import subprocess
import sys
import threading
import zipfile

import pytest

from kioku import packs

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def demo(**changes) -> packs.Pack:  # type: ignore[no-untyped-def]
    fields = dict(
        id="demo", title="Demo files", description="", version="1-1",
        site=("kioku_pack_demo",), drop=(), modules=("kioku_pack_demo",), imports=(),
        programs=("demo-tool",), env={"KIOKU_DEMO_DATA": "kioku_pack_demo/data"},
        own_files=("*.demodata",), size=0, unpacked=0, sha256="",
    )
    fields.update(changes)
    return packs.Pack(**fields)  # type: ignore[arg-type]


@pytest.fixture
def env(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("KIOKU_PACKS_DIR", str(tmp_path / "packs"))
    monkeypatch.delenv("KIOKU_DEMO_DATA", raising=False)
    pack = demo()
    monkeypatch.setattr(packs, "PACKS", [pack])
    for name in ("_bundled", "_pending", "_downloads"):
        monkeypatch.setattr(packs, name, {})
    for name in ("_asked", "_failed"):
        monkeypatch.setattr(packs, name, set())
    monkeypatch.setattr(packs, "_state_cache", None)
    monkeypatch.setattr(packs, "_site", [])
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    sys.modules.pop("kioku_pack_demo", None)
    yield tmp_path, pack
    sys.modules.pop("kioku_pack_demo", None)


def make_zip(path, files: dict[str, str]) -> str:  # type: ignore[no-untyped-def]
    with zipfile.ZipFile(path, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def addon(tmp_path, name: str, files: dict[str, str]) -> str:  # type: ignore[no-untyped-def]
    folder = tmp_path / "addons21" / name
    for rel, text in files.items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_text(text)
    (folder / "__init__.py").touch()
    return str(folder)


def test_needs_from_imports_and_program_names(env) -> None:  # type: ignore[no-untyped-def]
    tmp_path, pack = env
    assert packs.needs(addon(tmp_path, "a", {"x.py": "def f():\n    import kioku_pack_demo.sub\n"})) == [pack]
    assert packs.needs(addon(tmp_path, "b", {"x.py": "from kioku_pack_demo import cut\n"})) == [pack]
    assert packs.needs(addon(tmp_path, "c", {"x.py": "subprocess.run(['demo-tool.exe', path])\n"})) == [pack]
    assert packs.needs(addon(tmp_path, "d", {"x.py": "print('a demo-tool here')\n"})) == []
    # their own copy
    assert packs.needs(addon(tmp_path, "e", {"x.py": "import kioku_pack_demo\n",
                                              "lib/kioku_pack_demo/__init__.py": ""})) == []
    assert packs.needs(addon(tmp_path, "f", {"x.py": "run(['demo-tool'])\n", "data/eng.demodata": ""})) == []


def test_needs_caches_until_the_addon_changes(env) -> None:  # type: ignore[no-untyped-def]
    tmp_path, pack = env
    folder = addon(tmp_path, "a", {"x.py": "import os\n"})
    assert packs.needs(folder) == []
    assert packs._state()["scan"]["a"][2] == []
    with open(os.path.join(folder, "__init__.py"), "w") as f:
        f.write("import kioku_pack_demo\n")
    later = os.stat(folder).st_mtime_ns + 10**10
    os.utime(os.path.join(folder, "__init__.py"), ns=(later, later))
    assert packs.needs(folder) == [pack]


def test_setup_points_into_the_pack(env) -> None:  # type: ignore[no-untyped-def]
    tmp_path, pack = env
    packs.setup()
    assert packs.pack_dir(pack) in sys.path
    assert os.environ["KIOKU_DEMO_DATA"] == os.path.join(packs.pack_dir(pack), "kioku_pack_demo", "data")
    assert packs.status(pack) == "missing"


def test_bundled_files_win(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    tmp_path, pack = env
    site = tmp_path / "site"
    (site / "kioku_pack_demo").mkdir(parents=True)
    monkeypatch.setattr(sys, "path", [str(site)] + sys.path)
    packs.setup()
    assert packs.status(pack) == "bundled"
    assert packs.pack_dir(pack) not in sys.path
    assert "KIOKU_DEMO_DATA" not in os.environ


def test_import_from_an_addon_asks_for_the_pack(env) -> None:  # type: ignore[no-untyped-def]
    tmp_path, pack = env
    packs.setup()
    code = compile("import kioku_pack_demo", str(tmp_path / "addons21" / "1234" / "__init__.py"), "exec")
    with pytest.raises(ImportError):
        exec(code, {})
    assert packs._pending == {"demo": {"1234"}}
    assert "demo" in packs._failed


def test_imports_outside_addons_ask_nothing(env) -> None:  # type: ignore[no-untyped-def]
    """markdown probes pygments, Anki may probe modules: no offer for those."""
    tmp_path, pack = env
    packs.setup()
    code = compile("import kioku_pack_demo", str(tmp_path / "site-packages" / "markdown" / "x.py"), "exec")
    with pytest.raises(ImportError):
        exec(code, {})
    packs.program_started("demo-tool")
    assert packs._pending == {}


def test_declined_packs_are_not_offered_again(env) -> None:  # type: ignore[no-untyped-def]
    tmp_path, pack = env
    packs._set_declined([pack], True)
    packs.wanted(pack, "1234")
    assert packs._pending == {}
    packs.wanted(pack, "1234", force=True)
    assert packs._pending == {"demo": {"1234"}}


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # type: ignore[no-untyped-def]
        pass


@pytest.fixture
def server(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    served = tmp_path / "served"
    served.mkdir()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(served)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("KIOKU_PACKS_URL", f"http://127.0.0.1:{httpd.server_address[1]}/")
    yield served
    httpd.shutdown()


def test_download_installs_and_imports(env, server, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    tmp_path, pack = env
    files = {"kioku_pack_demo/__init__.py": "VALUE = 42\n", "kioku_pack_demo/data/x.txt": "data"}
    pack = demo(sha256=make_zip(server / pack.file, files))
    monkeypatch.setattr(packs, "PACKS", [pack])
    packs.setup()
    seen: list[int] = []
    packs.fetch(pack, seen.append)
    assert seen and seen[-1] == os.path.getsize(server / pack.file)
    assert packs.status(pack) == "installed"
    assert packs.disk_size(pack) == sum(len(t) for t in files.values())
    assert importlib.import_module("kioku_pack_demo").VALUE == 42
    assert not [n for n in os.listdir(packs.root()) if n.endswith((".part", ".new", ".old"))]

    # a new version in the app's manifest
    newer = demo(version="1-2", sha256=make_zip(server / "demo-1-2.zip", files))
    monkeypatch.setattr(packs, "PACKS", [newer])
    assert packs.status(newer) == "outdated"
    packs.fetch(newer)
    assert packs.status(newer) == "installed"

    packs.remove(newer)
    assert packs.status(newer) == "missing"


def test_damaged_download_is_refused(env, server, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    tmp_path, pack = env
    make_zip(server / pack.file, {"kioku_pack_demo/__init__.py": ""})
    pack = demo(sha256="0" * 64)
    with pytest.raises(ValueError, match="checksum"):
        packs.fetch(pack)
    assert packs.status(pack) == "missing"
    assert not os.listdir(packs.root())


def test_paths_outside_the_pack_are_refused(env) -> None:  # type: ignore[no-untyped-def]
    tmp_path, pack = env
    path = tmp_path / "bad.zip"
    make_zip(path, {"../evil.py": "x"})
    with pytest.raises(ValueError, match="unexpected path"):
        packs.install_file(pack, str(path))
    assert not (tmp_path / "evil.py").exists()


def test_shipped_manifest_is_built() -> None:
    """Every pack in packs.json has a built zip's size and checksum, and its
    files are left out of the bundles."""
    base, shipped = packs._load()
    assert base.startswith("https://") and base.endswith("/")
    assert len({p.id for p in shipped}) == len(shipped)
    for pack in shipped:
        assert pack.size > 0 and pack.unpacked > pack.size // 2 and len(pack.sha256) == 64, pack.id
        assert pack.modules or pack.programs or pack.imports, pack.id
    out = subprocess.run([sys.executable, os.path.join(ROOT, "shared", "tools", "packs.py"), "excludes"],
                         capture_output=True, text=True, check=True).stdout.split()
    assert out == [f"/{rel}/" for p in shipped for rel in p.site]


def test_addons_dialog_button_and_extra_files_dialog(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import types

    from aqt.qt import QApplication, QDialog, QLabel, QListWidget, QPushButton, QVBoxLayout

    app = QApplication.instance() or QApplication([])
    tmp_path, pack = env
    folder = addon(tmp_path, "1234", {"x.py": "import kioku_pack_demo\n"})
    packs.setup()

    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    view_files, config = QPushButton("View Files"), QPushButton("Config")
    addon_list = QListWidget()
    for widget in (addon_list, view_files, config):
        layout.addWidget(widget)
    dialog.form = types.SimpleNamespace(verticalLayout=layout, viewFiles=view_files, addonList=addon_list)  # type: ignore[attr-defined]
    dialog.mgr = types.SimpleNamespace(addonsFolder=lambda d: folder)  # type: ignore[attr-defined]
    dialog.selectedAddons = lambda: ["1234"]  # type: ignore[attr-defined]
    packs._on_addons_dialog(dialog)
    button = layout.itemAt(layout.indexOf(view_files) + 1).widget()
    assert button.text() == "Extra Files (1 needed)…"

    import aqt

    monkeypatch.setattr(aqt, "mw", types.SimpleNamespace(addonManager=types.SimpleNamespace(
        addonsFolder=lambda d: folder, addonName=lambda d: "Demo Add-on")), raising=False)
    extra = packs.ExtraFilesDialog(dialog, "1234")
    texts = [w.text() for w in extra.findChildren(QLabel)]
    assert "<b>Needed by Demo Add-on</b>" in texts
    assert any(t.startswith("Not downloaded") for t in texts)
    pack_dir = packs.pack_dir(pack)
    os.makedirs(pack_dir)
    with open(os.path.join(pack_dir, packs.INFO_FILE), "w") as f:
        f.write('{"version": "1-1", "unpacked": 2000000}')
    extra._refresh()
    texts = [w.text() for w in extra.findChildren(QLabel)]
    assert "Downloaded · 2.0 MB" in texts
    extra.close()
    app.processEvents()


def test_download_clears_not_now(env, server, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Downloading in Extra Files undoes an earlier Not now, so the offer
    comes back if the files are removed later."""
    import types
    from concurrent.futures import Future

    import aqt
    import aqt.utils

    tmp_path, pack = env
    pack = demo(sha256=make_zip(server / pack.file, {"kioku_pack_demo/__init__.py": ""}))
    monkeypatch.setattr(packs, "PACKS", [pack])

    def run_in_background(task, on_done, uses_collection=True):  # type: ignore[no-untyped-def]
        fut: Future = Future()
        try:
            fut.set_result(task())
        except Exception as e:
            fut.set_exception(e)
        on_done(fut)

    monkeypatch.setattr(aqt, "mw", types.SimpleNamespace(
        taskman=types.SimpleNamespace(run_in_background=run_in_background)), raising=False)
    monkeypatch.setattr(packs, "_parent", lambda: None)
    shown: list[str] = []
    monkeypatch.setattr(aqt.utils, "tooltip", lambda msg, **kw: shown.append(msg))
    monkeypatch.setattr(aqt.utils, "showWarning", lambda msg, **kw: shown.append(msg))
    packs._set_declined([pack], True)
    packs.download(pack)
    assert shown == ["Downloaded Demo files."]
    assert packs.status(pack) == "installed"
    assert packs._state()["declined"] == []
