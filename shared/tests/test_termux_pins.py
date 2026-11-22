"""The Termux runtime must run the Python and PyQt6 Anki pins, like the
native apps (test_anki_pins.py). It ran Termux's Python 3.14, and AnkiBrain
failed to load: its bundled httpcore sets __module__ on typing.Union, which
3.14 made immutable (issue #23). termux/tools/check_runtime_pins.py stops
build_bootstrap.sh when the prefix has another Python or PyQt6."""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
TOOLS = os.path.join(ROOT, "termux", "tools")
sys.path.insert(0, TOOLS)

import check_runtime_pins  # noqa: E402

PINS = {
    "PYTHON_VERSION": "3.13",
    "PYTHON_FULL_VERSION": "3.13.18",
    "PYQT6_VERSION": "6.11.0",
    "QT_VERSION": "6.11.2",
}


def make_prefix(root, python="3.13.18", pyqt="6.11.0", webengine="6.11.0", qt="6.11.2"):
    pyver = python.rsplit(".", 1)[0]
    inc = root / "include" / f"python{pyver}"
    inc.mkdir(parents=True)
    (inc / "patchlevel.h").write_text(f'#define PY_MAJOR_VERSION 3\n#define PY_VERSION              "{python}"\n')
    qtcore = root / "include" / "qt6" / "QtCore"
    qtcore.mkdir(parents=True)
    (qtcore / "qconfig.h").write_text(f'#define QT_VERSION_STR "{qt}"\n')
    site = root / "lib" / f"python{pyver}" / "site-packages"
    for name, version in (("pyqt6", pyqt), ("pyqt6_webengine", webengine)):
        info = site / f"{name}-{version}.dist-info"
        info.mkdir(parents=True)
        (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
    return root


def test_matching_runtime_passes(tmp_path) -> None:
    assert check_runtime_pins.check(str(make_prefix(tmp_path)), PINS) == ([], [])


def test_termux_python_fails(tmp_path) -> None:
    # Termux's own python 3.14 and its pyqt6 6.12
    prefix = make_prefix(tmp_path, python="3.14.10", pyqt="6.12.1")
    errors, _ = check_runtime_pins.check(str(prefix), PINS)
    assert len(errors) == 3
    assert "PYTHON_FULL_VERSION" in errors[0] and "3.13.18" in errors[0]


def test_other_pyqt_fails(tmp_path) -> None:
    errors, _ = check_runtime_pins.check(str(make_prefix(tmp_path, pyqt="6.12.1")), PINS)
    assert errors == ["PYQT6_VERSION: the runtime has 6.12.1, shared/versions.env pins 6.11.0"]


def test_other_qt_only_warns(tmp_path) -> None:
    # Qt still comes from the Termux repositories
    errors, warnings = check_runtime_pins.check(str(make_prefix(tmp_path, qt="6.12.0")), PINS)
    assert errors == []
    assert warnings == ["Qt 6.12.0 from the Termux repositories, Anki pins 6.11.2"]


def test_reads_versions_env() -> None:
    pins = check_runtime_pins.read_pins()
    assert re.fullmatch(r"3\.\d+", pins["PYTHON_VERSION"])
    assert pins["PYTHON_FULL_VERSION"].startswith(pins["PYTHON_VERSION"] + ".")


def test_bootstrap_uses_the_pins() -> None:
    with open(os.path.join(TOOLS, "build_bootstrap.sh")) as fh:
        script = fh.read()
    assert "check_runtime_pins.py build/rootfs-repo/usr" in script
    # the Python version comes from shared/versions.env, not a literal
    assert re.search(r'^PYVER="\$\{PYVER:-\$\(sed .*PYTHON_VERSION=.*versions\.env\)\}"$', script, re.M)
    # and PyQt6-sip too: the module Anki ships, not the newest of the ABI
    assert re.search(r'^PYQT6_SIP_VERSION="\$\(sed .*PYQT6_SIP_VERSION=.*versions\.env\)" \\\n\ttools/build_pyqt6_sip\.sh ', script, re.M)
