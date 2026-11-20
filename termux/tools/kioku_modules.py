"""The shared kioku modules (shared/python/kioku) the Termux app needs: every
`from kioku import x` / `import kioku.x` reachable from launch_anki.py,
including imports inside functions. build_bootstrap.sh copies these, so a
shared module that starts importing another can't leave it out of the app
(v0.2.9 shipped advanced.py without the gamepad.py it imports, and Anki
never started).

    python3 -I tools/kioku_modules.py [launch_anki.py] [shared/python/kioku]

prints one module name per line.
"""

from __future__ import annotations

import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAUNCHER = os.path.join(HERE, "..", "rootfs-overlay", "share", "ankidx", "launch_anki.py")
SHARED = os.path.join(HERE, "..", "..", "shared", "python", "kioku")


def imported_kioku_modules(path: str) -> set[str]:
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == "kioku":
                found.update(alias.name for alias in node.names)
            elif node.module.startswith("kioku."):
                found.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("kioku."):
                    found.add(alias.name.split(".")[1])
    return found


def needed_modules(launcher: str = LAUNCHER, shared: str = SHARED) -> list[str]:
    todo = sorted(imported_kioku_modules(launcher))
    seen: set[str] = set()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        path = os.path.join(shared, name + ".py")
        if not os.path.isfile(path):
            raise SystemExit(f"kioku.{name} is imported but {path} doesn't exist")
        seen.add(name)
        todo.extend(imported_kioku_modules(path) - seen)
    return sorted(seen)


if __name__ == "__main__":
    print("\n".join(needed_modules(*sys.argv[1:3])))
