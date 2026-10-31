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
