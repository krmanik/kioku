"""Kioku's dependencies at the versions the Anki release pins.

Add-ons are written and tested against desktop Anki's Python and packages, so
Kioku runs the same versions and moves only when Anki moves (AnkiHub's
bundled mashumaro broke when Kioku ran Python 3.14 and Anki 3.13). Anki pins
them in its source tree:

  .python-version       Python, e.g. 3.13.18
  qt/pyproject.toml     the [qt] extra: PyQt6, Qt (pyqt6-qt6), PyQt6-sip
  uv.lock               every Python package

Usage: python3 -I anki_pins.py <command> <anki dir> [<tag>]
  check        fail listing each pin in shared/versions.env and
               shared/requirements.txt that differs from Anki's
  update       rewrite shared/versions.env with Anki's pins
  constraints  print Anki's uv.lock pins for
               uv pip compile -c (shared/requirements.txt)
<anki dir> is a checkout (android/deps/anki), or with <tag> a git clone the
files are read from at that tag (a partial clone is enough).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "shared" / "versions.env"
REQUIREMENTS = ROOT / "shared" / "requirements.txt"


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


class Anki:
    def __init__(self, src: str, tag: str | None = None) -> None:
        self.src = src
        self.tag = tag

    def read(self, path: str) -> str:
        if self.tag:
            return subprocess.run(
                ["git", "-C", self.src, "show", f"{self.tag}:{path}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        return (Path(self.src) / path).read_text()

    def python(self) -> str:
        return self.read(".python-version").strip()

    def qt_extra(self) -> dict[str, str]:
        extras = tomllib.loads(self.read("qt/pyproject.toml"))["project"]["optional-dependencies"]
        pins = {}
        for req in extras["qt"]:
            name, version = req.split("==")
            pins[_norm(name)] = version.strip()
        return pins

    def lock(self) -> dict[str, str]:
        """uv.lock's packages that have one version (not Anki's own)."""
        versions: dict[str, set[str]] = {}
        for package in tomllib.loads(self.read("uv.lock"))["package"]:
            source = package.get("source", {})
            if "version" not in package or "editable" in source or "virtual" in source:
                continue
            versions.setdefault(_norm(package["name"]), set()).add(package["version"])
        return {name: v.pop() for name, v in versions.items() if len(v) == 1}


def wanted_versions_env(anki: Anki) -> dict[str, str]:
    """versions.env keys -> Anki's version."""
    python = anki.python()
    qt = anki.qt_extra()
    lock = anki.lock()
    return {
        "PYTHON_VERSION": ".".join(python.split(".")[:2]),
        "PYTHON_FULL_VERSION": python,
        "QT_VERSION": qt["pyqt6-qt6"],
        "PYQT6_VERSION": qt["pyqt6"],
        "PYQT6_SIP_VERSION": qt["pyqt6-sip"],
        "ORJSON_VERSION": lock["orjson"],
        "RPDS_VERSION": lock["rpds-py"],
        "MARKUPSAFE_VERSION": lock["markupsafe"],
    }


def read_versions_env(text: str) -> dict[str, str]:
    return dict(re.findall(r"^([A-Z0-9_]+)=(.*)$", text, re.M))


def read_requirements(text: str) -> dict[str, str]:
    pins = {}
    for m in re.finditer(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==([^\s;\\]+)", text, re.M):
        pins[_norm(m[1])] = m[2]
    return pins


def differences(anki: Anki, versions_env: str, requirements: str) -> list[str]:
    problems = []
    have = read_versions_env(versions_env)
    for key, version in wanted_versions_env(anki).items():
        if have.get(key) != version:
            problems.append(f"shared/versions.env {key}={have.get(key, '(missing)')}, Anki pins {version}")
    lock = anki.lock()
    for name, version in read_requirements(requirements).items():
        if name in lock and lock[name] != version:
            problems.append(f"shared/requirements.txt {name}=={version}, Anki pins {lock[name]}")
    return problems


def updated_versions_env(anki: Anki, text: str) -> str:
    for key, version in wanted_versions_env(anki).items():
        line = f"{key}={version}"
        text, n = re.subn(rf"^{key}=.*$", line, text, flags=re.M)
        if not n:
            raise SystemExit(f"shared/versions.env has no {key}=")
    return text


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4) or argv[1] not in ("check", "update", "constraints"):
        print(__doc__, file=sys.stderr)
        return 2
    anki = Anki(argv[2], argv[3] if len(argv) == 4 else None)
    if argv[1] == "check":
        problems = differences(anki, VERSIONS.read_text(), REQUIREMENTS.read_text())
        for p in problems:
            print(p)
        return 1 if problems else 0
    if argv[1] == "update":
        VERSIONS.write_text(updated_versions_env(anki, VERSIONS.read_text()))
        return 0
    for name, version in sorted(anki.lock().items()):
        print(f"{name}=={version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
