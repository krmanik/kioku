"""kioku.prefs: Anki's first start writes prefs21.db without committing it.
An app killed before the first profile save (on the first-run language
dialog, say) left a prefs21.db that the next start called corrupt."""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

import pytest
from aqt.profiles import ProfileManager

from kioku import prefs


def killed_first_start(tmp_path: Path) -> Path:
    """The files on disk when the app is killed during Anki's first start:
    _loadMeta has run (the first-run language dialog comes next), nothing is
    committed yet. Copied while the connection is still open, as a kill
    leaves them."""
    first = tmp_path / "first"
    first.mkdir()
    pm = ProfileManager(first)
    assert pm._loadMeta().firstTime
    killed = tmp_path / "killed"
    killed.mkdir()
    for name in os.listdir(first):
        if name.startswith(prefs.FILE):
            shutil.copy(first / name, killed / name)
    pm.db.close()
    return killed


@pytest.fixture
def original_load_meta():
    load_meta = ProfileManager._loadMeta
    yield load_meta
    ProfileManager._loadMeta = load_meta


def test_without_the_fix_the_next_start_says_corrupt(tmp_path, original_load_meta) -> None:
    killed = killed_first_start(tmp_path)
    result = ProfileManager(killed)._loadMeta()
    assert result.loadError  # main.py then shows "Preferences Corrupt"


def test_the_next_start_is_a_first_start(tmp_path, original_load_meta) -> None:
    killed = killed_first_start(tmp_path)
    prefs.install()
    pm = ProfileManager(killed)
    result = pm.setupMeta()
    assert not result.loadError
    assert result.firstTime  # the language dialog comes again
    pm.db.close()


def test_an_empty_file_is_an_interrupted_start(tmp_path) -> None:
    (tmp_path / prefs.FILE).write_bytes(b"")
    assert prefs.remove_interrupted(str(tmp_path))
    assert not (tmp_path / prefs.FILE).exists()


def saved_prefs(base: Path, *profiles: str) -> Path:
    pm = ProfileManager(base)
    pm.setupMeta()
    for name in profiles:
        pm.create(name)
    pm.db.commit()
    pm.db.close()
    return base / prefs.FILE


def test_saved_settings_stay(tmp_path, original_load_meta) -> None:
    path = saved_prefs(tmp_path)
    assert not prefs.remove_interrupted(str(tmp_path))
    assert path.exists()


def test_profiles_without_settings_stay(tmp_path, original_load_meta) -> None:
    # Anki's own warning fits this one: the profiles are still listed
    path = saved_prefs(tmp_path, "User 1")
    db = sqlite3.connect(path)
    db.execute("delete from profiles where name = '_global'")
    db.commit()
    db.close()
    assert not prefs.remove_interrupted(str(tmp_path))
    assert path.exists()


def test_a_file_sqlite_cant_read_is_left_to_anki(tmp_path) -> None:
    path = tmp_path / prefs.FILE
    path.write_bytes(b"not a database" * 100)
    assert not prefs.remove_interrupted(str(tmp_path))
    assert path.exists()


def test_termux_and_native_apps_install_it() -> None:
    root = Path(__file__).resolve().parents[2]
    launcher = (root / "termux/rootfs-overlay/share/ankidx/launch_anki.py").read_text()
    patches = (root / "shared/python/kioku/patches.py").read_text()
    assert "prefs.install()" in launcher
    assert "prefs.install()" in patches
