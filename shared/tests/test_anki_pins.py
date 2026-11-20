"""Kioku runs the Python, Qt, PyQt6 and Python packages the Anki release pins
(shared/tools/anki_pins.py). Kioku ran Python 3.14 while Anki 26.09.4 pins
3.13.18, and AnkiHub stopped loading on the iPhone: its bundled mashumaro
3.15 can't handle Optional fields on 3.14 ("UnserializableField: Field "tags"
of type Optional[List[str]] in NoteInfo is not serializable")."""

from __future__ import annotations

import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "shared", "tools"))

import anki_pins  # noqa: E402

ANKI = os.path.join(ROOT, "android", "deps", "anki")  # shared/tests/run.sh


def _read(path: str) -> str:
    with open(os.path.join(ROOT, path)) as f:
        return f.read()


def test_versions_match_anki() -> None:
    problems = anki_pins.differences(
        anki_pins.Anki(ANKI), _read("shared/versions.env"), _read("shared/requirements.txt")
    )
    assert problems == [], "run shared/tools/anki_pins.py update (see shared/requirements.in):\n" + "\n".join(problems)


def test_tests_run_on_anki_python() -> None:
    # shared/tests/run.sh makes its venv with Anki's Python
    assert "%d.%d" % sys.version_info[:2] == anki_pins.wanted_versions_env(anki_pins.Anki(ANKI))["PYTHON_VERSION"]


def test_drift_is_reported(tmp_path) -> None:
    anki = tmp_path / "anki"
    (anki / "qt").mkdir(parents=True)
    (anki / ".python-version").write_text("3.13.18\n")
    (anki / "qt" / "pyproject.toml").write_text(
        '[project.optional-dependencies]\nqt = ["pyqt6==6.11.0", "pyqt6-qt6==6.11.2", "pyqt6_sip==13.12.0"]\n'
    )
    (anki / "uv.lock").write_text(
        "".join(
            f'[[package]]\nname = "{n}"\nversion = "{v}"\n\n'
            for n, v in [("orjson", "3.12.0"), ("rpds-py", "2026.6.3"), ("MarkupSafe", "3.0.3"), ("idna", "3.19")]
        )
        + '[[package]]\nname = "aqt"\nversion = "0.0.0"\nsource = { editable = "qt" }\n'
    )
    env = (
        "PYTHON_VERSION=3.14\nPYTHON_FULL_VERSION=3.14.8\nQT_VERSION=6.11.2\nPYQT6_VERSION=6.11.0\n"
        "PYQT6_SIP_VERSION=13.12.0\nORJSON_VERSION=3.12.0\nRPDS_VERSION=2026.6.3\nMARKUPSAFE_VERSION=3.0.3\n"
    )
    problems = anki_pins.differences(anki_pins.Anki(str(anki)), env, "idna==3.20\n    # via requests\nqtpy==2.4.3\n")
    assert problems == [
        "shared/versions.env PYTHON_VERSION=3.14, Anki pins 3.13",
        "shared/versions.env PYTHON_FULL_VERSION=3.14.8, Anki pins 3.13.18",
        "shared/requirements.txt idna==3.20, Anki pins 3.19",
    ]
    fixed = anki_pins.updated_versions_env(anki_pins.Anki(str(anki)), env)
    assert anki_pins.differences(anki_pins.Anki(str(anki)), fixed, "idna==3.19\n") == []
