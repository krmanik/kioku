"""The Termux app ships only some of shared/python/kioku (termux/tools/
kioku_modules.py picks them for build_bootstrap.sh). v0.2.9 left out
gamepad.py, which advanced.py imports, so Anki never started inside the
desktop (issue #13). Lay the modules out as the app does and import them
the way launch_anki.py does."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
TOOLS = os.path.join(ROOT, "termux", "tools")
ANKIDX = os.path.join(ROOT, "termux", "rootfs-overlay", "share", "ankidx")
SHARED = os.path.join(ROOT, "shared", "python", "kioku")
sys.path.insert(0, TOOLS)

import kioku_modules  # noqa: E402


def test_finds_imports_inside_functions(tmp_path) -> None:
    (tmp_path / "launch.py").write_text("from kioku import a\n")
    shared = tmp_path / "kioku"
    shared.mkdir()
    (shared / "a.py").write_text("def f():\n    from kioku import b\n")
    (shared / "b.py").write_text("import kioku.c\n")
    (shared / "c.py").write_text("")
    (shared / "unused.py").write_text("")
    assert kioku_modules.needed_modules(str(tmp_path / "launch.py"), str(shared)) == ["a", "b", "c"]


def test_missing_module_fails_the_build(tmp_path) -> None:
    (tmp_path / "launch.py").write_text("from kioku import gone\n")
    (tmp_path / "kioku").mkdir()
    with pytest.raises(SystemExit, match="kioku.gone"):
        kioku_modules.needed_modules(str(tmp_path / "launch.py"), str(tmp_path / "kioku"))


def test_shipped_modules_import(tmp_path) -> None:
    modules = kioku_modules.needed_modules()
    assert {"advanced", "gamepad", "syncserver", "ankidroid", "maindocks"} <= set(modules)
    # share/ankidx as build_bootstrap.sh lays it out: launch_anki.py's helpers
    # and kioku/ with only the shipped modules
    ankidx = tmp_path / "ankidx"
    shutil.copytree(ANKIDX, ankidx, ignore=shutil.ignore_patterns("__pycache__"))
    (ankidx / "kioku").mkdir()
    for name in modules:
        shutil.copy(os.path.join(SHARED, name + ".py"), ankidx / "kioku")
    # every module, as launch_anki.py and Preferences › Advanced import them,
    # with shared/python (and its other kioku modules) off the path
    script = f"""
import importlib, sys
sys.path = [p for p in sys.path if not p.rstrip("/").endswith("shared/python")]
sys.path.insert(0, {str(ankidx)!r})
import kioku
assert list(kioku.__path__) == [{str(ankidx / "kioku")!r}], kioku.__path__
for name in {modules!r}:
    importlib.import_module("kioku." + name)
import kioku_platform
assert kioku_platform.__file__.startswith({str(ankidx)!r})
print("ok")
"""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH="")
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
