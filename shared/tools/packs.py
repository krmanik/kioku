#!/usr/bin/env python3
"""Extra files for add-ons (shared/python/kioku/packs.json, kioku/packs.py):
leave them out of the app bundles, build their zips, publish them.

  packs.py excludes        rsync patterns for the bundles: each pack's files
                           (ios/tools/bundle_python.sh, android/tools/pack_python.sh)
  packs.py build [SITE...] zip each pack from a site-packages folder (default:
                           ios/build/site, then android/build/site) into
                           build/packs/ and write size/unpacked/sha256 into
                           packs.json. A pack whose version has a published
                           zip must not change: bump its version instead.
  packs.py publish         commit build/packs/*.zip to the packs branch (its
                           files are served from raw.githubusercontent.com)
                           and push it. Old versions stay for older apps.
"""

from __future__ import annotations

import fnmatch
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST = os.path.join(ROOT, "shared", "python", "kioku", "packs.json")
OUT = os.path.join(ROOT, "build", "packs")
BRANCH = "packs"
BRANCH_DIR = os.path.join(ROOT, "build", "packs-branch")


def load() -> dict:
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def save(data: dict) -> None:
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def file_name(pack: dict) -> str:
    return f"{pack['id']}-{pack['version']}.zip"


def excludes() -> None:
    for pack in load()["packs"]:
        for rel in pack["site"]:
            print(f"/{rel}/")


def _files(site: str, pack: dict) -> list[str]:
    """Paths relative to site, sorted, without the pack's drop patterns."""
    found = []
    for rel in pack["site"]:
        for top in glob.glob(os.path.join(site, rel)):
            for base, dirs, names in os.walk(top):
                dirs[:] = sorted(d for d in dirs if d != "__pycache__")
                for name in names:
                    path = os.path.relpath(os.path.join(base, name), site).replace(os.sep, "/")
                    if not any(fnmatch.fnmatch(path, p) for p in pack["drop"]) and not name.endswith(".pyc"):
                        found.append(path)
    return sorted(found)


def build(sites: list[str]) -> None:
    sites = sites or [os.path.join(ROOT, "ios", "build", "site"), os.path.join(ROOT, "android", "build", "site")]
    data = load()
    os.makedirs(OUT, exist_ok=True)
    for pack in data["packs"]:
        site = next((s for s in sites if all(glob.glob(os.path.join(s, r)) for r in pack["site"])), None)
        if site is None:
            sys.exit(f"{pack['id']}: {pack['site']} not found in {sites} (build the app first)")
        files = _files(site, pack)
        out = os.path.join(OUT, file_name(pack))
        unpacked = 0
        with zipfile.ZipFile(out + ".tmp", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for rel in files:
                info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
                info.external_attr = 0o644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(os.path.join(site, rel), "rb") as f:
                    content = f.read()
                unpacked += len(content)
                z.writestr(info, content, compresslevel=9)
        os.replace(out + ".tmp", out)
        with open(out, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        if pack["sha256"] and pack["sha256"] != digest and _published(file_name(pack)):
            sys.exit(f"{pack['id']} {pack['version']} is published with other files: bump its version")
        pack.update(size=os.path.getsize(out), unpacked=unpacked, sha256=digest)
        print(f"{file_name(pack)}: {len(files)} files, {unpacked / 1e6:.1f} MB → {pack['size'] / 1e6:.1f} MB")
    save(data)


def _git(*args: str, cwd: str = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def _published(name: str) -> bool:
    return _git("cat-file", "-e", f"origin/{BRANCH}:{name}", check=False).returncode == 0


def publish() -> None:
    data = load()
    names = [file_name(p) for p in data["packs"]]
    missing = [n for n in names if not os.path.exists(os.path.join(OUT, n))]
    if missing:
        sys.exit(f"build first: {missing}")
    has_branch = _git("ls-remote", "--exit-code", "--heads", "origin", BRANCH, check=False).returncode == 0
    if not os.path.isdir(BRANCH_DIR):
        if has_branch:
            _git("fetch", "origin", BRANCH)
            _git("worktree", "add", "-B", BRANCH, BRANCH_DIR, f"origin/{BRANCH}")
        else:
            _git("worktree", "add", "--detach", BRANCH_DIR)
            _git("checkout", "--orphan", BRANCH, cwd=BRANCH_DIR)
            _git("rm", "-rfq", ".", cwd=BRANCH_DIR)
    elif has_branch:
        _git("fetch", "origin", BRANCH)
        _git("reset", "--hard", f"origin/{BRANCH}", cwd=BRANCH_DIR)
    with open(os.path.join(BRANCH_DIR, "README.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Kioku extra files for add-ons\n\n"
            "Downloaded by the Kioku apps when an add-on needs them (Tools › Add-ons › Extra Files).\n"
            "Built by `shared/tools/packs.py` on the main branch; listed in "
            "`shared/python/kioku/packs.json`. Old versions stay for older apps.\n\n"
            "| File | Contents | License |\n| --- | --- | --- |\n"
            "| jieba-*.zip | [jieba](https://github.com/fxsjy/jieba) | MIT |\n"
            "| pygments-*.zip | [Pygments](https://pygments.org) | BSD-2-Clause |\n"
            "| tesseract-data-*.zip | [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) "
            "and Tesseract's configs | Apache-2.0 |\n"
            "| espeak-data-*.zip | [eSpeak NG](https://github.com/espeak-ng/espeak-ng)'s data, compiled "
            "by `shared/tools/build_programs.sh` | GPL-3.0-or-later |\n"
        )
    for name in names:
        target = os.path.join(BRANCH_DIR, name)
        if not os.path.exists(target):
            shutil.copy2(os.path.join(OUT, name), target)
    _git("add", "-A", cwd=BRANCH_DIR)
    if _git("diff", "--cached", "--quiet", cwd=BRANCH_DIR, check=False).returncode == 0:
        print("nothing new to publish")
        return
    _git("commit", "-qm", "Extra files: " + ", ".join(names), cwd=BRANCH_DIR)
    _git("push", "origin", f"HEAD:{BRANCH}", cwd=BRANCH_DIR)
    print(f"published {names} on {BRANCH}")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "excludes":
        excludes()
    elif command == "build":
        build(sys.argv[2:])
    elif command == "publish":
        publish()
    else:
        sys.exit(__doc__)
