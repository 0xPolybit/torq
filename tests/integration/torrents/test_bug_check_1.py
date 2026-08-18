"""Bug Check 1 — engine basics.

These integration tests run after slice 0.9. They target the three
properties called out in PLAN §45: ID stability, pause/resume
idempotency, and remove-with-data correctness on a real libtorrent
session. They run only when libtorrent is installed (CI) and skip
locally.

The bug-check file is intentionally separate from the per-slice
integration suite so reviewers can run just the bug-check points.
"""

from __future__ import annotations

from pathlib import Path

import pytest

lt = pytest.importorskip("libtorrent")

from torq.torrents.libtorrent_engine import (  # noqa: E402
    LibtorrentEngine,
)
from torq.torrents.models import AddOptions  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "torrents"
TORRENT_PATH = FIXTURES / "torq-test-payload.bin.torrent"

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


# -- ID stability -------------------------------------------------------


async def test_bug1_id_stable_across_add_remove_add(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    """Adding the same torrent twice yields the same id."""
    ref_a = await engine.add_magnet(DEBIAN_MAGNET, AddOptions(save_path=tmp_path))
    await engine.remove(ref_a.id)
    ref_b = await engine.add_magnet(DEBIAN_MAGNET, AddOptions(save_path=tmp_path))
    assert ref_a.id == ref_b.id
    assert ref_a.info_hash_v1 == ref_b.info_hash_v1


# -- pause / resume idempotency -----------------------------------------


async def test_bug1_pause_is_idempotent(engine: LibtorrentEngine, tmp_path: Path) -> None:
    ref = await engine.add_magnet(DEBIAN_MAGNET, AddOptions(save_path=tmp_path))
    await engine.pause(ref.id)
    # Second pause should not raise.
    await engine.pause(ref.id)
    # Status should still report the torrent as paused/stopped.
    status = await engine.status(ref.id)
    assert status.state.value in {
        "paused",
        "stalled_download",
        "stalled_upload",
        "metadata",
    }


async def test_bug1_resume_is_idempotent(engine: LibtorrentEngine, tmp_path: Path) -> None:
    ref = await engine.add_magnet(DEBIAN_MAGNET, AddOptions(save_path=tmp_path))
    # Resume on already-active torrent should not raise.
    await engine.resume(ref.id)
    await engine.resume(ref.id)


# -- remove with data ---------------------------------------------------


async def test_bug1_remove_with_data_deletes_files(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    """remove(torrent_id, delete_data=True) must remove downloaded files.

    The test does not depend on a successful download — instead it
    pre-creates the files libtorrent expects (from the torrent's file
    list) so that ``options_t.delete_files`` has something to remove.
    """
    # Parse the torrent locally to learn the file name.
    from torq.util.torrent_file import parse_torrent_file

    meta = parse_torrent_file(TORRENT_PATH)
    assert len(meta.files) == 1
    expected_path = tmp_path / meta.files[0].path

    # Plant the file so remove(delete_data=True) has something to delete.
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    expected_path.write_bytes(b"\x00" * meta.total_size)

    ref = await engine.add_torrent_file(TORRENT_PATH, AddOptions(save_path=tmp_path))
    await engine.remove(ref.id, delete_data=True)

    assert not expected_path.exists(), f"remove(delete_data=True) left {expected_path} behind"


async def test_bug1_remove_without_data_keeps_files(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    """remove(torrent_id, delete_data=False) must not touch the filesystem."""
    from torq.util.torrent_file import parse_torrent_file

    meta = parse_torrent_file(TORRENT_PATH)
    expected_path = tmp_path / meta.files[0].path
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    expected_path.write_bytes(b"\x00" * meta.total_size)

    ref = await engine.add_torrent_file(TORRENT_PATH, AddOptions(save_path=tmp_path))
    await engine.remove(ref.id, delete_data=False)

    assert expected_path.exists(), f"remove(delete_data=False) unexpectedly removed {expected_path}"
