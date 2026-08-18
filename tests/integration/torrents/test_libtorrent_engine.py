"""Integration tests for :class:`LibtorrentEngine`.

These tests require libtorrent to be installed. On environments without
libtorrent, the entire module is skipped via :func:`pytest.importorskip`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

lt = pytest.importorskip("libtorrent")

from torq.torrents.libtorrent_engine import (  # noqa: E402
    LibtorrentEngine,
)
from torq.torrents.models import AddOptions  # noqa: E402

# A public magnet (Debian netinst ISO). The test does not depend on
# download completion — it only validates that the magnet was added.
DEBIAN_MAGNET = (
    "magnet:?xt=urn:btih:4d68447ca5b4147459e4be6b44389efb8177c2fb"
    "&dn=debian-12.5.0-amd64-netinst.iso"
    "&tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A80"
)


@pytest.fixture
async def engine() -> LibtorrentEngine:
    """Yield a started engine that is stopped on teardown."""
    e = LibtorrentEngine()
    await e.start()
    try:
        yield e
    finally:
        await e.stop()


def test_engine_constructs_when_libtorrent_present() -> None:
    engine = LibtorrentEngine()
    assert engine is not None


async def test_engine_lifecycle_starts_a_session(engine: LibtorrentEngine) -> None:
    assert engine._session is not None


async def test_engine_stop_clears_session() -> None:
    e = LibtorrentEngine()
    await e.start()
    assert e._session is not None
    await e.stop()
    assert e._session is None


async def test_engine_add_magnet_yields_ref_with_v1_hash(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    ref = await engine.add_magnet(
        DEBIAN_MAGNET, AddOptions(save_path=tmp_path)
    )
    assert ref.info_hash_v1 is not None
    assert len(ref.info_hash_v1) == 40
    assert ref.id == ref.info_hash_v1


async def test_engine_list_contains_added_torrent(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    ref = await engine.add_magnet(
        DEBIAN_MAGNET, AddOptions(save_path=tmp_path)
    )
    statuses = await engine.list()
    ids = {s.id for s in statuses}
    assert ref.id in ids


async def test_engine_status_lookup_returns_torrent_status(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    ref = await engine.add_magnet(
        DEBIAN_MAGNET, AddOptions(save_path=tmp_path)
    )
    status = await engine.status(ref.id)
    assert status.id == ref.id
    assert status.total_size is not None
    assert status.total_size > 0


async def test_engine_status_raises_for_unknown_id(
    engine: LibtorrentEngine,
) -> None:
    with pytest.raises(KeyError):
        await engine.status("deadbeef" * 5)
