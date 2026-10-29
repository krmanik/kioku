"""From the Ya-Alex/anki-addons data.parquet, write names.json (id -> title,
likes) and github-ids.txt: add-ons missing from the dump that support Anki
2.1.50+ and have a GitHub repo ("<id> <user>/<repo>" per line).

    uv run --with pyarrow python -I names.py <data.parquet> <addons dir> <out dir>

data.parquet: https://huggingface.co/datasets/Ya-Alex/anki-addons
(history/<date>/parquet/data.parquet).
"""

import json
import os
import sys

import pyarrow.parquet as pq

parquet, addons, out = sys.argv[1:4]
rows = pq.read_table(parquet, columns=["id", "anki_web", "github"]).to_pylist()
have = set(os.listdir(addons))


def max_point_version(r):
    web = r["anki_web"] or {}
    branches = web.get("branches") or []
    return max([b["max_point_version"] or 0 for b in branches] + [web.get("anki_point_version") or 0])


names = {}
with open(os.path.join(out, "github-ids.txt"), "w") as f:
    for r in rows:
        web, gh = r["anki_web"] or {}, r["github"] or {}
        if web:
            names[str(r["id"])] = dict(t=web["title"], likes=web["likes"] or 0, pv=web["anki_point_version"])
        if str(r["id"]) not in have and max_point_version(r) >= 50 and gh.get("repo"):
            f.write(f"{r['id']} {gh['user']}/{gh['repo']}\n")
json.dump(names, open(os.path.join(out, "names.json"), "w"))
