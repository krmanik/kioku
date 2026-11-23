"""The sync server as a child process (kioku.syncserver._ServerProcess): what
Anki builds without Kioku's rsbridge patch use, such as the Termux variant's."""

from __future__ import annotations

import os
import socket
import types
import urllib.request

import pytest

from kioku import syncserver
from test_syncserver import NORMAL, Required, add_note, fronts, login, new_col, settings, sync, url


@pytest.fixture(autouse=True)
def upstream_rsbridge(monkeypatch):  # type: ignore[no-untyped-def]
    # only upstream's blocking syncserver(): no syncserver_start/_stop
    monkeypatch.setattr(syncserver, "_rsbridge", lambda: types.SimpleNamespace())
    yield
    syncserver.stop()


def test_start_stop_restart(platform) -> None:
    s = settings()
    st = syncserver.start(s)
    assert st.running and st.port == s.port, st
    child = syncserver._process._child
    assert child is not None and child.poll() is None
    assert syncserver.answers()
    assert not any(k.startswith("SYNC_USER") for k in os.environ)

    syncserver.stop()
    assert child.poll() is not None
    assert not syncserver.status().running
    with pytest.raises(OSError):
        urllib.request.urlopen(f"{url(st)}health", timeout=2)

    # starting again while running replaces the child on the same port
    assert syncserver.start(s).running
    first = syncserver._process._child
    assert syncserver.start(s).running and syncserver.answers()
    assert first.poll() is not None


def test_port_in_use(platform) -> None:
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        st = syncserver.start(settings(port=busy.getsockname()[1]))
    assert not st.running
    assert "already in use" in st.error, st.error
    assert syncserver._process._child is None


def test_round_trip(platform, tmp_path) -> None:
    s = settings()
    st = syncserver.start(s)
    a = new_col(tmp_path / "a" / "collection.anki2")
    b = new_col(tmp_path / "b" / "collection.anki2")
    try:
        add_note(a, "from a")
        auth_a = login(a, s, url(st))
        auth_b = login(b, s, url(st))
        assert sync(a, auth_a, upload=True) in (Required.FULL_SYNC, Required.FULL_UPLOAD)
        assert sync(b, auth_b, upload=False) in (Required.FULL_SYNC, Required.FULL_DOWNLOAD)
        assert fronts(b) == {"from a"}
        add_note(b, "from b")
        assert sync(b, auth_b) in NORMAL
        assert sync(a, auth_a) in NORMAL
        assert fronts(a) == {"from a", "from b"}
        assert syncserver.has_data(s)
    finally:
        a.close()
        b.close()


def test_collection_size_limit_is_raised() -> None:
    # issue #28: upstream's 100 (a 300 MB collection) put big collections in
    # a full-sync loop
    assert int(syncserver.MAX_SYNC_PAYLOAD_MEGS) >= 1024


@pytest.mark.parametrize("megs", ["1", "2"])
def test_collection_size_limit(platform, tmp_path, monkeypatch, megs) -> None:
    # issue #28 scaled down: the limit is 3 x MAX_SYNC_PAYLOAD_MEGS of
    # collection. A child process reads it fresh, so each limit can be tried
    monkeypatch.setenv("MAX_SYNC_PAYLOAD_MEGS", "unset")
    monkeypatch.delenv("MAX_SYNC_PAYLOAD_MEGS")
    monkeypatch.setattr(syncserver, "MAX_SYNC_PAYLOAD_MEGS", megs)
    s = settings()
    st = syncserver.start(s)
    col = new_col(tmp_path / "a" / "collection.anki2")
    try:
        # 4 MB of collection that compresses well: over a 3 MB limit, under 6
        add_note(col, "big", "x" * (4 * 1024 * 1024))
        auth = login(col, s, url(st))
        if megs == "1":
            with pytest.raises(Exception, match="exceeds size limit"):
                sync(col, auth, upload=True, media=False)
        else:
            sync(col, auth, upload=True, media=False)
            # then normal syncs, not a full sync forced on every sync
            add_note(col, "after")
            assert sync(col, auth, media=False) in NORMAL
            assert sync(col, auth, media=False) in NORMAL
    finally:
        if col.db is None:
            # the backend reopened it after the refused upload
            col.reopen(after_full_sync=True)
        col.close()
