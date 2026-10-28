#!/usr/bin/env python3
"""Resolve and download the runtime's .deb closure from Termux apt repositories.

Local .deb files (e.g. packages from krmanik/termux-packages that are not in the
official repos yet) take precedence over repository packages of the same name,
and over those in an earlier --local directory.

  tools/fetch_debs.py --roots anki,jwm,st,... --local build/anki-debs --local local-debs --out build/debs
"""
import argparse
import hashlib
import http.client
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from debs_to_prefix import ar_members, control_field  # noqa: E402

REPOS = {
    "main": "https://packages-cf.termux.dev/apt/termux-main/dists/stable/main/binary-aarch64/Packages",
    "x11": "https://packages-cf.termux.dev/apt/termux-x11/dists/x11/main/binary-aarch64/Packages",
}
REPO_BASE = {
    "main": "https://packages-cf.termux.dev/apt/termux-main/",
    "x11": "https://packages-cf.termux.dev/apt/termux-x11/",
}


def fetch(url, attempts=5):
    # The Termux CDN rejects Python's default User-Agent.
    req = urllib.request.Request(url, headers={"User-Agent": "Debian APT-HTTP/1.3 (kioku)"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        # the CDN sometimes drops a connection mid-file
        except (OSError, http.client.HTTPException) as e:
            if attempt == attempts - 1:
                raise
            print(f"retrying {url}: {e}", file=sys.stderr)
            time.sleep(2 ** attempt)


def parse_index(text, repo):
    pkgs = {}
    for block in text.split("\n\n"):
        fields = {}
        for line in block.splitlines():
            if line and not line[0].isspace() and ":" in line:
                k, v = line.split(":", 1)
                fields[k] = v.strip()
        if "Package" in fields:
            fields["_repo"] = repo
            pkgs[fields["Package"]] = fields
    return pkgs


def dep_names(fields):
    out = []
    for key in ("Pre-Depends", "Depends"):
        for dep in fields.get(key, "").split(","):
            dep = dep.strip()
            if dep:
                # First alternative wins, as apt does by default.
                out.append(re.sub(r"\(.*?\)", "", dep.split("|")[0]).strip())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", required=True, help="comma separated package names")
    ap.add_argument("--local", action="append", default=[],
                    help="directory with local .deb files that override the repos (repeatable; skipped if missing)")
    ap.add_argument("--skip", default="", help="comma separated packages not to download (pruned anyway)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--list", help="write 'package<TAB>version' of the closure here")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    pkgs = {}
    for repo, url in REPOS.items():
        print(f"index {repo}: {url}")
        for name, fields in parse_index(fetch(url).decode(), repo).items():
            pkgs.setdefault(name, fields)

    local = {}
    for local_dir in a.local:
        if not os.path.isdir(local_dir):
            continue
        for f in sorted(os.listdir(local_dir)):
            if f.endswith(".deb"):
                path = os.path.join(local_dir, f)
                members = dict(ar_members(path))
                control = next(v for k, v in members.items() if k.startswith("control.tar"))
                name = control_field(control, "Package")
                fields = {"Package": name, "Version": control_field(control, "Version"),
                          "Depends": control_field(control, "Depends") or "", "_local": path}
                local[name] = fields
                pkgs[name] = fields

    provides = {}
    for name, fields in pkgs.items():
        for p in fields.get("Provides", "").split(","):
            p = re.sub(r"\(.*?\)", "", p).strip()
            if p:
                provides.setdefault(p, name)

    skip = {s for s in a.skip.split(",") if s}
    seen, missing = set(), set()
    stack = [r for r in a.roots.split(",") if r]
    while stack:
        n = stack.pop()
        name = n if n in pkgs else provides.get(n)
        if not name:
            missing.add(n)
            continue
        if name in seen:
            continue
        seen.add(name)
        stack.extend(dep_names(pkgs[name]))
    if missing:
        sys.exit(f"unresolvable: {sorted(missing)}")

    total = 0
    wanted = set()
    for name in sorted(seen):
        fields = pkgs[name]
        if name in skip:
            continue
        if "_local" in fields:
            dest = os.path.join(a.out, os.path.basename(fields["_local"]))
            wanted.add(os.path.basename(dest))
            with open(fields["_local"], "rb") as src, open(dest, "wb") as dst:
                dst.write(src.read())
            print(f"local {name} {fields['Version']}")
            continue
        dest = os.path.join(a.out, os.path.basename(fields["Filename"]))
        wanted.add(os.path.basename(dest))
        want = fields["SHA256"]
        if not (os.path.exists(dest) and hashlib.sha256(open(dest, "rb").read()).hexdigest() == want):
            data = fetch(REPO_BASE[fields["_repo"]] + fields["Filename"])
            if hashlib.sha256(data).hexdigest() != want:
                sys.exit(f"checksum mismatch for {name}")
            with open(dest, "wb") as fh:
                fh.write(data)
        total += int(fields.get("Size", 0))
    # Older versions left from earlier runs would be unpacked too, by tools/debs_to_prefix.py.
    for f in os.listdir(a.out):
        if f.endswith(".deb") and f not in wanted:
            os.remove(os.path.join(a.out, f))
            print(f"removed stale {f}")
    print(f"{len(seen)} packages ({len(seen & skip)} skipped), {total / 2**20:.0f} MiB from repos -> {a.out}")

    if a.list:
        with open(a.list, "w") as fh:
            for name in sorted(seen - skip):
                fh.write(f"{name}\t{pkgs[name]['Version']}\n")


if __name__ == "__main__":
    main()
