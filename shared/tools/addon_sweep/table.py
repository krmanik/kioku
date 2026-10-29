"""Print classify.py's output as the Markdown in docs/addon-deps.md.

    python3 -I table.py <classified.json> > table.md
"""

import json, sys
from collections import Counter
rows = json.load(open(sys.argv[1]))
flag = [r for r in rows if r["c"]]
cnt = Counter(k for r in rows for k in r["c"])
mods = Counter(m for r in rows for k in ("native", "pure") for m in r["c"].get(k, []) if not m.startswith("ships"))
tools = Counter(t for r in rows for t in r["c"].get("tool", []))
j = lambda r, k: ", ".join(r["c"].get(k, [])) if r["c"].get(k) is not True else "yes"
print(f"Add-ons scanned: {len(rows)}. Nothing outside Kioku's bundle: {len(rows)-len(flag)}. Flagged: {len(flag)}.\n")
print("| Need | Add-ons |\n|---|---|")
for k, label in (("tool", "External program (subprocess)"), ("native", "Native library or shipped binaries"),
                 ("pure", "Pure-Python library not bundled"), ("os", "Windows/macOS/Linux desktop API"),
                 ("removed", "Module removed from Python 3.13+"), ("addon", "Another add-on"),
                 ("pip", "Runs pip at runtime")):
    print(f"| {label} | {cnt[k]} |")
print("\nMost wanted programs: " + ", ".join(f"{t} {n}" for t, n in tools.most_common(12)) + ".\n")
print("Most wanted libraries: " + ", ".join(f"{t} {n}" for t, n in mods.most_common(15)) + ".\n")
print("| Add-on | ID | Likes | Programs | Native libs | Pure libs | Desktop API | Removed stdlib | Other add-on | pip |")
print("|---|---|---|---|---|---|---|---|---|---|")
for r in sorted(flag, key=lambda r: -r["likes"]):
    t = r["title"].replace("|", "/")[:50]
    print(f"| {t} | {r['id']} | {r['likes']} | " + " | ".join(j(r, k) for k in ("tool", "native", "pure", "os", "removed", "addon", "pip")) + " |")
