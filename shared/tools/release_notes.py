"""Write the notes of one Kioku release (Markdown) to stdout.

"What's new" is the version's section of the manual's changes page
(docs/manual/src/changes.md, "## <version>"), with its links pointing at the
published manual. Below it go the install steps (release_install.md) and a
link to the full changelog. .github/workflows/release.yml uses it when it
publishes a release.
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
parser.add_argument("--repo", required=True, help="owner/name on GitHub")
parser.add_argument("--previous", help="the tag of the release before this one")
args = parser.parse_args()


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


new = whats_new(args.version)
if new is None:
    print(f"no '## {args.version}' section in changes.md", file=sys.stderr)
    sys.exit(1)
install = string.Template((pathlib.Path(__file__).parent / "release_install.md").read_text())
print("## What's new\n")
print(new + "\n")
print(install.substitute(version=args.version, repo=args.repo))
if args.previous:
    print(
        f"**Full Changelog**: https://github.com/{args.repo}/compare/"
        f"{args.previous}...v{args.version}"
    )
