"""Write the notes of one Kioku release (Markdown) to stdout.

A download table (release_download.md) comes first. "What's new" is the version's section of the manual's changes page
(docs/manual/src/changes.md, "## <version>"), with its links pointing at the
published manual. Below it go the install steps (release_install.md) and a
link to the full changelog. .github/workflows/release.yml uses it when it
publishes a release.

--testflight prints only "What's new" as plain text for TestFlight's "What to
Test" (and ios/appstore/whats_new.txt): one line per item, no Markdown, as
TestFlight shows every newline and no formatting.
"""

import argparse
import pathlib
import re
import string
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANUAL = "https://krmanik.github.io/kioku/"

parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True)
parser.add_argument("--repo", help="owner/name on GitHub (needed without --testflight)")
parser.add_argument("--previous", help="the tag of the release before this one")
parser.add_argument("--testflight", action="store_true",
                    help="plain-text What's new for TestFlight's What to Test")
args = parser.parse_args()
if not args.testflight and not args.repo:
    parser.error("--repo is required")


def whats_new(version: str) -> str | None:
    changes = (ROOT / "docs/manual/src/changes.md").read_text()
    match = re.search(
        rf"^## {re.escape(version)}\n(.*?)(?=^## |\Z)", changes, re.M | re.S
    )
    if not match:
        return None
    text = match.group(1).strip()

    # manual pages: using/addons.md#x -> <manual>/using/addons.html#x
    def link(m: re.Match) -> str:
        target = m.group(1)
        if re.match(r"[a-z]+:", target):
            return m.group(0)
        target = re.sub(r"\.md(?=#|$)", ".html", target)
        return f"]({MANUAL}{target})"

    text = re.sub(r"\]\(([^)\s]+)\)", link, text)

    # GitHub shows every newline of a release's notes: unwrap the manual's
    # paragraphs and list items
    lines: list[str] = []
    for line in text.splitlines():
        starts = not line.strip() or re.match(r"\s*([-*>#|]|\d+\.)\s", line)
        if lines and lines[-1].strip() and not starts:
            lines[-1] += " " + line.strip()
        else:
            lines.append(line)
    return "\n".join(lines)


def plain(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)\s]+\)", r"\1", text)  # [text](url) -> text
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = text.replace("`", "")
    text = re.sub(r"^(\s*)[-*] ", r"\1• ", text, flags=re.M)
    return re.sub(r"\n{2,}", "\n", text)


new = whats_new(args.version)
if new is None:
    print(f"no '## {args.version}' section in changes.md", file=sys.stderr)
    sys.exit(1)
if args.testflight:
    print(plain(new))
    sys.exit(0)
here = pathlib.Path(__file__).parent
download = string.Template((here / "release_download.md").read_text())
install = string.Template((here / "release_install.md").read_text())
print(download.substitute(version=args.version, repo=args.repo))
print("## What's new\n")
print(new + "\n")
print(install.substitute(version=args.version, repo=args.repo))
if args.previous:
    print(
        f"**Full Changelog**: https://github.com/{args.repo}/compare/"
        f"{args.previous}...v{args.version}"
    )
