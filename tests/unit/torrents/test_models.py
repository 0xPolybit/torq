"""Unit tests for torrent domain models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import pytest

from torq.torrents.models import (
    AddOptions,
    SourceType,
    Torrent,
    TorrentFile,
    TorrentRef,
    TorrentState,
    TorrentStatus,
    TransferLimits,
)


def test_torrent_state_values_are_stable_strings() -> None:
    """Wire values must match the values persisted in SQLite and on the API."""
    assert TorrentState.METADATA.value == "metadata"
    assert TorrentState.QUEUED.value == "queued"
    assert TorrentState.CHECKING.value == "checking"
    assert TorrentState.DOWNLOADING.value == "downloading"
    assert TorrentState.STALLED_DOWNLOAD.value == "stalled_download"
    assert TorrentState.PAUSED.value == "paused"
    assert TorrentState.COMPLETED.value == "completed"
    assert TorrentState.SEEDING.value == "seeding"
    assert TorrentState.STALLED_UPLOAD.value == "stalled_upload"
    assert TorrentState.ERROR.value == "error"
    assert TorrentState.REMOVED.value == "removed"


def test_source_type_values() -> None:
    assert SourceType.MAGNET.value == "magnet"
    assert SourceType.TORRENT_FILE.value == "torrent_file"
    assert SourceType.TORRENT_URL.value == "torrent_url"


def test_torrent_ref_is_frozen() -> None:
    ref = TorrentRef(id="abc123", info_hash_v1="abc123", info_hash_v2=None)
    with pytest.raises(FrozenInstanceError):
        ref.id = "different"  # type: ignore[misc]


def test_torrent_ref_accepts_v2_only() -> None:
    ref = TorrentRef(id="v2hash", info_hash_v1=None, info_hash_v2="v2hash")
    assert ref.id == "v2hash"
    assert ref.info_hash_v1 is None
    assert ref.info_hash_v2 == "v2hash"


def test_add_options_save_path_required() -> None:
    opts = AddOptions(save_path=Path("/tmp/downloads"))
    assert opts.save_path == Path("/tmp/downloads")
    assert opts.start_paused is False
    assert opts.sequential is False
    assert opts.category is None
    assert opts.file_priorities == ()


def test_add_options_file_priorities_is_tuple_of_tuples() -> None:
    opts = AddOptions(
        save_path=Path("/tmp"),
        file_priorities=((0, 0), (3, 7)),
    )
    assert opts.file_priorities == ((0, 0), (3, 7))


def test_transfer_limits_default_unlimited() -> None:
    limits = TransferLimits()
    assert limits.download_bytes_per_second == 0
    assert limits.upload_bytes_per_second == 0


def test_torrent_status_required_fields() -> None:
    status = TorrentStatus(
        id="abc",
        name="test",
        state=TorrentState.DOWNLOADING,
        progress=0.5,
        total_size=1000,
        downloaded=500,
        uploaded=10,
        download_rate=100,
        upload_rate=10,
        seeds=5,
        peers=2,
        ratio=0.02,
        eta_seconds=60,
        queue_position=None,
    )
    assert status.error_message is None


def test_torrent_full_record() -> None:
    now = datetime.now(timezone.utc)
    record = Torrent(
        id="abc",
        name="full-record",
        source_type=SourceType.MAGNET,
        source="magnet:?xt=urn:btih:abc",
        save_path=Path("/tmp"),
        state=TorrentState.SEEDING,
        progress=1.0,
        total_size=1000,
        downloaded=1000,
        uploaded=5000,
        download_rate=0,
        upload_rate=50,
        seeds=10,
        peers=0,
        ratio=5.0,
        eta_seconds=None,
        added_at=now,
    )
    assert record.completed_at is None
    assert record.queue_position is None


def test_torrent_file_defaults_to_normal_priority() -> None:
    f = TorrentFile(index=0, path="foo.bin", size_bytes=10)
    assert f.priority == 4


@pytest.mark.parametrize(
    "priority",
    [0, 1, 4, 7],
)
def test_torrent_file_accepts_valid_priorities(priority: int) -> None:
    f = TorrentFile(index=1, path="bar.bin", size_bytes=10, priority=priority)
    assert f.priority == priority