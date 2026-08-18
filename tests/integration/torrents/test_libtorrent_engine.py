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
from torq.torrents.models import AddOptions, TransferLimits  # noqa: E402
from torq.torrents.priorities import FilePriority  # noqa: E402

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
    ref = await engine.add_magnet(DEBIAN_MAGNET, AddOptions(save_path=tmp_path))
    assert ref.info_hash_v1 is not None
    assert len(ref.info_hash_v1) == 40
    assert ref.id == ref.info_hash_v1


async def test_engine_list_contains_added_torrent(engine: LibtorrentEngine, tmp_path: Path) -> None:
    ref = await engine.add_magnet(DEBIAN_MAGNET, AddOptions(save_path=tmp_path))
    statuses = await engine.list()
    ids = {s.id for s in statuses}
    assert ref.id in ids


async def test_engine_status_lookup_returns_torrent_status(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    ref = await engine.add_magnet(DEBIAN_MAGNET, AddOptions(save_path=tmp_path))
    status = await engine.status(ref.id)
    assert status.id == ref.id
    assert status.total_size is not None
    assert status.total_size > 0


async def test_engine_status_raises_for_unknown_id(
    engine: LibtorrentEngine,
) -> None:
    with pytest.raises(KeyError):
        await engine.status("deadbeef" * 5)


# -- pause / resume / remove / recheck ---------------------------------


async def test_engine_pause_then_status_shows_paused(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    ref = await engine.add_magnet(DEBIAN_MAGNET, AddOptions(save_path=tmp_path))
    await engine.pause(ref.id)
    status = await engine.status(ref.id)
    assert status.state.value in {"paused", "stalled_download", "stalled_upload"}


async def test_engine_resume_after_pause_is_idempotent(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    ref = await engine.add_magnet(DEBIAN_MAGNET, AddOptions(save_path=tmp_path))
    # Resume on an already-active torrent should be a no-op (no exception).
    await engine.resume(ref.id)
    await engine.resume(ref.id)
    statuses = await engine.list()
    assert any(s.id == ref.id for s in statuses)


async def test_engine_pause_then_resume(engine: LibtorrentEngine, tmp_path: Path) -> None:
    ref = await engine.add_magnet(DEBIAN_MAGNET, AddOptions(save_path=tmp_path))
    await engine.pause(ref.id)
    await engine.resume(ref.id)
    status = await engine.status(ref.id)
    assert status.state.value not in {"paused"}


async def test_engine_remove_drops_torrent(engine: LibtorrentEngine, tmp_path: Path) -> None:
    ref = await engine.add_magnet(DEBIAN_MAGNET, AddOptions(save_path=tmp_path))
    await engine.remove(ref.id)
    with pytest.raises(KeyError):
        await engine.status(ref.id)


async def test_engine_remove_unknown_id_raises(
    engine: LibtorrentEngine,
) -> None:
    with pytest.raises(KeyError):
        await engine.remove("deadbeef" * 5)


async def test_engine_pause_unknown_id_raises(
    engine: LibtorrentEngine,
) -> None:
    with pytest.raises(KeyError):
        await engine.pause("deadbeef" * 5)


async def test_engine_resume_unknown_id_raises(
    engine: LibtorrentEngine,
) -> None:
    with pytest.raises(KeyError):
        await engine.resume("deadbeef" * 5)


async def test_engine_recheck_does_not_raise(engine: LibtorrentEngine, tmp_path: Path) -> None:
    ref = await engine.add_magnet(DEBIAN_MAGNET, AddOptions(save_path=tmp_path))
    await engine.recheck(ref.id)
    # Status remains queryable after recheck.
    status = await engine.status(ref.id)
    assert status.id == ref.id


async def test_engine_recheck_unknown_id_raises(
    engine: LibtorrentEngine,
) -> None:
    with pytest.raises(KeyError):
        await engine.recheck("deadbeef" * 5)


async def test_engine_add_magnet_with_start_paused(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    ref = await engine.add_magnet(DEBIAN_MAGNET, AddOptions(save_path=tmp_path, start_paused=True))
    status = await engine.status(ref.id)
    # The torrent may have started fetching metadata, but the paused flag
    # should at minimum be reflected in the state mapping (either PAUSED,
    # METADATA, or STALLED_*) — assert it is not in the active set.
    assert status.state.value in {
        "paused",
        "stalled_download",
        "stalled_upload",
        "metadata",
    }


# -- file priorities + transfer limits -----------------------------------


async def test_engine_set_file_priority_accepts_known_value(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    """set_file_priority accepts a valid 0..7 priority on a known file."""
    # Use the test fixture torrent so we have a known file index and
    # so the metadata is available immediately.
    from tests.integration.torrents.test_bug_check_1 import TORRENT_PATH

    ref = await engine.add_torrent_file(TORRENT_PATH, AddOptions(save_path=tmp_path))
    await engine.set_file_priority(ref.id, 0, int(FilePriority.HIGH))
    # No assertion on internals — the call must simply not raise.


async def test_engine_set_file_priority_rejects_out_of_range(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    """set_file_priority validates the priority range."""
    from tests.integration.torrents.test_bug_check_1 import TORRENT_PATH

    ref = await engine.add_torrent_file(TORRENT_PATH, AddOptions(save_path=tmp_path))
    with pytest.raises(ValueError):
        await engine.set_file_priority(ref.id, 0, 8)
    with pytest.raises(ValueError):
        await engine.set_file_priority(ref.id, 0, -1)


async def test_engine_set_file_priority_unknown_id_raises(
    engine: LibtorrentEngine,
) -> None:
    with pytest.raises(KeyError):
        await engine.set_file_priority("deadbeef" * 5, 0, 4)


async def test_engine_set_limits_per_torrent(engine: LibtorrentEngine, tmp_path: Path) -> None:
    from tests.integration.torrents.test_bug_check_1 import TORRENT_PATH

    ref = await engine.add_torrent_file(TORRENT_PATH, AddOptions(save_path=tmp_path))
    await engine.set_limits(
        ref.id,
        TransferLimits(download_bytes_per_second=200_000, upload_bytes_per_second=100_000),
    )
    # Look it up — the call must succeed and the torrent must remain listed.
    statuses = await engine.list()
    assert any(s.id == ref.id for s in statuses)


async def test_engine_set_limits_rejects_negative(engine: LibtorrentEngine, tmp_path: Path) -> None:
    from tests.integration.torrents.test_bug_check_1 import TORRENT_PATH

    ref = await engine.add_torrent_file(TORRENT_PATH, AddOptions(save_path=tmp_path))
    with pytest.raises(ValueError):
        await engine.set_limits(
            ref.id,
            TransferLimits(download_bytes_per_second=-1, upload_bytes_per_second=0),
        )


async def test_engine_set_limits_unknown_id_raises(
    engine: LibtorrentEngine,
) -> None:
    with pytest.raises(KeyError):
        await engine.set_limits(
            "deadbeef" * 5,
            TransferLimits(download_bytes_per_second=0, upload_bytes_per_second=0),
        )


async def test_engine_set_global_limits(
    engine: LibtorrentEngine,
) -> None:
    """Global limits apply to the session and don't raise."""
    await engine.set_global_limits(
        TransferLimits(download_bytes_per_second=1_000_000, upload_bytes_per_second=500_000)
    )


async def test_engine_set_global_limits_rejects_negative(
    engine: LibtorrentEngine,
) -> None:
    with pytest.raises(ValueError):
        await engine.set_global_limits(
            TransferLimits(download_bytes_per_second=-1, upload_bytes_per_second=0)
        )


async def test_engine_add_torrent_file_with_file_priorities(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    """file_priorities passed at add time are accepted."""
    from tests.integration.torrents.test_bug_check_1 import TORRENT_PATH

    ref = await engine.add_torrent_file(
        TORRENT_PATH,
        AddOptions(save_path=tmp_path, file_priorities=((0, 0),)),  # don't download
    )
    status = await engine.status(ref.id)
    assert status.id == ref.id


async def test_engine_add_torrent_file_rejects_invalid_file_priority(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    from tests.integration.torrents.test_bug_check_1 import TORRENT_PATH

    with pytest.raises(ValueError):
        await engine.add_torrent_file(
            TORRENT_PATH,
            AddOptions(save_path=tmp_path, file_priorities=((0, 99),)),
        )


async def test_engine_add_torrent_file_rejects_out_of_range_file_index(
    engine: LibtorrentEngine, tmp_path: Path
) -> None:
    from tests.integration.torrents.test_bug_check_1 import TORRENT_PATH

    with pytest.raises(ValueError):
        await engine.add_torrent_file(
            TORRENT_PATH,
            AddOptions(save_path=tmp_path, file_priorities=((99, 4),)),
        )
