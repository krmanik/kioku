"""orjson 3.12.0 builds the JSONDecodeError's doc string by writing into
PyUnicode_New's result without a NULL check. When CPython can't allocate it,
loads() crashed the app (TestFlight 0.2.11, iPad: SIGSEGV at 0x38 in
pyunicode_fourbyte under raise_loads_exception) instead of raising.
shared/patches/orjson-loads-error-doc.patch builds the doc with
PyUnicode_FromStringAndSize and falls back to "". iOS and Android apply it in
fetch_deps.sh; the web build copies the iOS sdist."""

from __future__ import annotations

import os
import re
import subprocess

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
PATCH = os.path.join(ROOT, "shared", "patches", "orjson-loads-error-doc.patch")


def _orjson_version() -> str:
    with open(os.path.join(ROOT, "shared", "versions.env")) as f:
        return re.search(r"^ORJSON_VERSION=(\S+)", f.read(), re.M).group(1)


@pytest.mark.parametrize("target", ["ios", "android"])
def test_fetch_deps_applies_patch(target: str) -> None:
    with open(os.path.join(ROOT, target, "tools", "fetch_deps.sh")) as f:
        script = f.read()
    assert "shared/patches/orjson-loads-error-doc.patch" in script


def test_web_builds_from_ios_sdist() -> None:
    with open(os.path.join(ROOT, "web", "tools", "build_orjson.sh")) as f:
        assert "ios/deps/sdist/orjson-" in f.read()


@pytest.mark.parametrize("target", ["ios", "android"])
def test_patch_is_applied_to_sdist(target: str) -> None:
    sdist = os.path.join(ROOT, target, "deps", "sdist", f"orjson-{_orjson_version()}")
    if not os.path.isdir(sdist):
        pytest.skip(f"{target} deps not fetched")
    with open(PATCH) as f:
        done = subprocess.run(
            ["patch", "-R", "-s", "-f", "--dry-run", "-d", sdist, "-p1"],
            stdin=f,
            capture_output=True,
        )
    assert done.returncode == 0, done.stdout + done.stderr
    with open(os.path.join(sdist, "src", "exception.rs")) as f:
        assert "PyUnicode_FromStringAndSize" in f.read()
