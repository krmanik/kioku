"""Add-ons' own program copies map to Kioku's bundled programs
(kioku.programs.program_name), and the program folder stays out of the cache
folder, which Android empties while the app runs when storage is low."""

from __future__ import annotations

import os

from kioku import programs


def test_program_names_from_add_on_copies() -> None:
    names = {
        "support/mecab.lin": "mecab",  # Japanese Support, AJT Japanese
        "support/cwebp.mac": "cwebp",  # AJT Media Converter
        "ffmpeg.exe": "ffmpeg",
        "mecab/mecab-linux": "mecab",  # Migaku Kanji GOD
        "mecab/mecab-macos": "mecab",
        "mecab/mecab-windows.exe": "mecab",
        "bin/ffmpeg-linux-x86_64": "ffmpeg",
        "/usr/bin/tesseract": "tesseract",
        "lame": "lame",
        "espeak-ng": "espeak-ng",
    }
    for path, name in names.items():
        assert programs.program_name(path) == name, path


def test_program_folder_under_given_base(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(programs.subprocess, "Popen", programs.subprocess.Popen)
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    programs.install(str(tmp_path))
    assert programs._bin_dir == os.path.join(str(tmp_path), "kioku-bin")
    assert os.path.isdir(programs._bin_dir)


def test_which_finds_bundled_programs_where_access_denies_exec(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # iPhone: access(X_OK) is no for every file in the app's data folder,
    # so shutil.which() found none of the bundled programs
    import shutil

    monkeypatch.setattr(programs.subprocess, "Popen", programs.subprocess.Popen)
    monkeypatch.setattr(programs, "_bin_dir", programs._bin_dir)
    monkeypatch.setattr(programs, "_native", {"ffmpeg"})
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    programs.install(str(tmp_path))
    real_access = os.access
    monkeypatch.setattr(os, "access", lambda p, m, **kw: False if m & os.X_OK else real_access(p, m))
    assert shutil.which("ffmpeg", path=programs._bin_dir) is None  # what add-ons got
    stub = os.path.join(programs._bin_dir, "ffmpeg")
    assert programs._which_bundled("ffmpeg") == stub
    assert programs._which_bundled(b"ffmpeg") == os.fsencode(stub)
    assert programs._which_bundled("ffmpeg", path="/usr/bin") is None  # not on that path
    assert programs._which_bundled("not-bundled") is None


def test_stubs_without_exec_mode_get_it(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(programs.subprocess, "Popen", programs.subprocess.Popen)
    monkeypatch.setattr(programs, "_bin_dir", programs._bin_dir)
    monkeypatch.setattr(programs, "_native", {"ffmpeg"})
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    stub = tmp_path / "kioku-bin" / "ffmpeg"
    stub.parent.mkdir()
    stub.write_text("#!/bin/sh\n")
    stub.chmod(0o644)
    programs.install(str(tmp_path))
    assert stub.stat().st_mode & 0o111
