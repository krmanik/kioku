#!/usr/bin/env python3
"""Check that the runtime prefix has the Python and PyQt6 Anki pins.

Add-ons are tested against desktop Anki's versions: on Termux's Python 3.14
AnkiBrain failed to load (its bundled httpcore sets __module__ on
typing.Union, which 3.14 made immutable; issue #23). Kioku's shared/versions.env
holds the versions the Anki release pins (shared/tools/anki_pins.py); the
Termux runtime takes Python, PyQt6 and PyQt6-WebEngine from the
krmanik/termux-packages release anki-<ANKI_TAG>, built for them.

Qt still comes from the Termux repositories (6.12): a different Qt is
reported, not fatal, until Kioku builds Qt for Termux too.

  tools/check_runtime_pins.py build/rootfs-repo/usr
"""
import argparse
import glob
import os
import re
import sys

VERSIONS_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../shared/versions.env")


def read_pins(path=VERSIONS_ENV):
    pins = {}
    with open(path) as fh:
        for line in fh:
            m = re.match(r"([A-Z0-9_]+)=(.*)", line.strip())
            if m:
                pins[m.group(1)] = m.group(2).strip('"')
    return pins


def _define(path, name):
    try:
        with open(path) as fh:
            m = re.search(rf'#define {name}\s+"([^"]+)"', fh.read())
    except FileNotFoundError:
        return None
    return m.group(1) if m else None


def _dist_version(site, project):
    for info in glob.glob(os.path.join(site, "*.dist-info")):
        name = os.path.basename(info)[: -len(".dist-info")].rsplit("-", 1)[0]
        if name.lower().replace("_", "-") != project:
            continue
        with open(os.path.join(info, "METADATA")) as fh:
            for line in fh:
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
    return None


def runtime_versions(prefix, pyver):
    site = os.path.join(prefix, "lib", f"python{pyver}", "site-packages")
    return {
        "PYTHON_FULL_VERSION": _define(os.path.join(prefix, "include", f"python{pyver}", "patchlevel.h"), "PY_VERSION"),
        "PYQT6_VERSION": _dist_version(site, "pyqt6"),
        "PYQT6_WEBENGINE_VERSION": _dist_version(site, "pyqt6-webengine"),
        "QT_VERSION": _define(os.path.join(prefix, "include", "qt6", "QtCore", "qconfig.h"), "QT_VERSION_STR"),
    }


def check(prefix, pins):
    """Return (errors, warnings)."""
    pyver = pins["PYTHON_VERSION"]
    found = runtime_versions(prefix, pyver)
    want = {
        "PYTHON_FULL_VERSION": pins["PYTHON_FULL_VERSION"],
        "PYQT6_VERSION": pins["PYQT6_VERSION"],
        # PyQt6-WebEngine is released with PyQt6 and Anki pins the same version
        "PYQT6_WEBENGINE_VERSION": pins["PYQT6_VERSION"],
    }
    errors = []
    for key, value in want.items():
        if found[key] != value:
            have = found[key] or f"none (no Python {pyver} in the prefix?)"
            errors.append(f"{key}: the runtime has {have}, shared/versions.env pins {value}")
    warnings = []
    if found["QT_VERSION"] != pins["QT_VERSION"]:
        warnings.append(f"Qt {found['QT_VERSION']} from the Termux repositories, Anki pins {pins['QT_VERSION']}")
    return errors, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prefix")
    a = ap.parse_args()
    errors, warnings = check(a.prefix, read_pins())
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        sys.exit("runtime differs from Anki's pins:\n  " + "\n  ".join(errors))
    print("runtime matches Anki's Python and PyQt6 pins")


if __name__ == "__main__":
    main()
