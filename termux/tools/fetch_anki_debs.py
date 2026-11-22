#!/usr/bin/env python3
"""Download the .debs of the krmanik/termux-packages release anki-<version>.

That release holds the packages the Termux repositories don't have, built by
the repository's anki workflow: anki, and the Python packages built for the
Python Anki pins (python, python-pip, pyqt6, python-pyqt6-webengine,
python-rpds-py, python-markupsafe, python-orjson), which take the place of
the repositories' builds for their newer Python. The version defaults to ANKI_TAG in shared/versions.env.

  tools/fetch_anki_debs.py --out build/anki-debs [--version 26.09.3]

.debs in OUT that are not in the release are removed. GITHUB_TOKEN, when set,
is sent with the API request (GitHub allows 60 requests an hour without it).
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

REPO = os.environ.get("ANKI_DEBS_REPO", "krmanik/termux-packages")
VERSIONS_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../shared/versions.env")


def anki_tag():
    with open(VERSIONS_ENV) as fh:
        for line in fh:
            if line.startswith("ANKI_TAG="):
                return line.split("=", 1)[1].strip()
    sys.exit(f"no ANKI_TAG in {VERSIONS_ENV}")


def fetch(url, accept=None):
    headers = {"User-Agent": "kioku"}
    if accept:
        headers["Accept"] = accept
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--version", default=None, help="Anki version (default: ANKI_TAG in shared/versions.env)")
    a = ap.parse_args()

    tag = f"anki-{a.version or anki_tag()}"
    try:
        release = json.loads(fetch(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}",
                                   "application/vnd.github+json"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sys.exit(f"no release {tag} in {REPO}: run its anki workflow first")
        raise
    assets = [x for x in release["assets"] if x["name"].endswith(".deb")]
    if not assets:
        sys.exit(f"release {tag} in {REPO} has no .debs")

    os.makedirs(a.out, exist_ok=True)
    names = {x["name"] for x in assets}
    for f in os.listdir(a.out):
        if f.endswith(".deb") and f not in names:
            os.remove(os.path.join(a.out, f))

    for asset in assets:
        dest = os.path.join(a.out, asset["name"])
        want = (asset.get("digest") or "").removeprefix("sha256:")
        if want and os.path.exists(dest) and hashlib.sha256(open(dest, "rb").read()).hexdigest() == want:
            continue
        data = fetch(asset["browser_download_url"])
        if want and hashlib.sha256(data).hexdigest() != want:
            sys.exit(f"checksum mismatch for {asset['name']}")
        with open(dest, "wb") as fh:
            fh.write(data)
        print(f"{tag}: {asset['name']}")


if __name__ == "__main__":
    main()
