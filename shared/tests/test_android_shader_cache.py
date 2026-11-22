"""Android: Qt's shader disk cache is off and an old one is removed. The
emulator's GPU driver wrote a 1.8 GB program binary, which Qt read at every
start: Kioku took 3 GB of memory and stopped responding (tablet-size
emulator, 2026-11-23). The package needs _kioku_android, so the function is
taken from its source."""

from __future__ import annotations

import ast
import os
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "android/python/kioku_platform/__init__.py"


def load(cache: Path, environ: dict) -> dict:
    tree = ast.parse(SOURCE.read_text())
    wanted = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == "_no_shader_disk_cache")
              or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "SHADER_CACHE_PREFIX" for t in n.targets))]
    assert len(wanted) == 2
    import shutil

    fake_os = type("FakeOs", (), {"environ": environ, "listdir": staticmethod(os.listdir),
                                  "path": os.path})
    ns = {"os": fake_os, "shutil": shutil, "cache_dir": lambda: str(cache)}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns


def test_cache_off_and_old_cache_removed(tmp_path) -> None:
    old = tmp_path / "qtshadercache-arm64-little_endian-lp64"
    old.mkdir()
    (old / "1d911de7").write_bytes(b"x" * 1024)
    (tmp_path / "WebView").mkdir()
    environ: dict = {}
    load(tmp_path, environ)["_no_shader_disk_cache"]()
    assert environ["QT_DISABLE_SHADER_DISK_CACHE"] == "1"
    assert not old.exists()
    assert (tmp_path / "WebView").exists()  # the rest of the cache stays


def test_runs_before_qt() -> None:
    tree = ast.parse(SOURCE.read_text())
    prepare = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "prepare")
    calls = [c.func.id for c in ast.walk(prepare) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)]
    assert "_no_shader_disk_cache" in calls
