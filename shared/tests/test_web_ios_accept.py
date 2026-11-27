"""Issue #34: the iOS file picker greys out files whose extension has no
system type when the input's `accept` lists it, so Install from file could
not choose a .ankiaddon. web/shell/kioku-web.js pick() keeps `accept` on iOS
only when iOS knows every entry."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
JS = os.path.join(ROOT, "web", "shell", "kioku-web.js")


def _knows_all(accepts: list[str]) -> list[bool]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    with open(JS) as f:
        src = f.read()
    types = re.search(r"const IOS_TYPES = new Set\(\[.*?\]\);", src, re.S).group(0)
    func = re.search(r"function iosKnowsAll\(accept\) \{.*?\n  \}", src, re.S).group(0)
    code = f"{types}\n{func}\nconsole.log(JSON.stringify({json.dumps(accepts)}.map(iosKnowsAll)));"
    out = subprocess.run([node, "-e", code], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_anki_types_drop_accept() -> None:
    assert _knows_all([".ankiaddon", ".apkg,.colpkg", ".txt,.apkg"]) == [False, False, False]


def test_known_types_keep_accept() -> None:
    assert _knows_all([".jpg,.png", ".TXT, .csv", "image/*", ""]) == [True, True, True, True]


def test_pick_uses_check() -> None:
    with open(JS) as f:
        assert "!(isIOS() && !iosKnowsAll(accept))" in f.read()
