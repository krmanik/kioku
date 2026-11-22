"""prefs21.db left behind by an interrupted first start.

On its first start Anki creates prefs21.db and writes the global settings
into it without committing them; the first commit comes with the first
profile save. Phone apps are often killed before that (Android stops apps in
the background, and the first-run language dialog waits for a tap), which
left a prefs21.db without the global settings. The next start called it
corrupt ("Preferences Corrupt ... add them back using the same names").

Such a file holds no profile, so nothing can be lost: remove it before Anki
reads it, and Anki starts as on a first run. A file with any profile in it,
or one sqlite can't read, is left to Anki.
"""

from __future__ import annotations

import os
import sqlite3

FILE = "prefs21.db"


def interrupted_first_run(path: str) -> bool:
    """True when the prefs21.db at path has no profile and no settings."""
    if not os.path.isfile(path):
        return False
    if os.path.getsize(path) == 0:
        return True
    try:
        # not read-only: a hot journal from the killed start is rolled back
        db = sqlite3.connect(path)
        try:
            tables = [r[0] for r in db.execute("select name from sqlite_master where type = 'table'")]
            if not tables:
                return True
            if tables != ["profiles"]:
                return False
            return db.execute("select count() from profiles").fetchone()[0] == 0
        finally:
            db.close()
    except sqlite3.Error:
        return False


def remove_interrupted(base: str) -> bool:
    """Remove base/prefs21.db (and its journal) when a first start was
    interrupted; True when it did."""
    path = os.path.join(base, FILE)
    if not interrupted_first_run(path):
        return False
    for suffix in ("", "-journal", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass
    print(f"kioku: removed {path} left by an interrupted first start")
    return True


def install() -> None:
    from aqt.profiles import ProfileManager

    load_meta = ProfileManager._loadMeta

    def load_meta_after_interrupted_start(self, retrying: bool = False):  # type: ignore[no-untyped-def]
        if not retrying:
            try:
                remove_interrupted(self.base)
            except OSError as e:
                print(f"kioku: {FILE}: {e}")
        return load_meta(self, retrying)

    ProfileManager._loadMeta = load_meta_after_interrupted_start
