"""Domain models for the torrent engine layer.

These types are deliberately independent of libtorrent — the libtorrent
adapter maps engine-native values into these shapes in one place (see
``libtorrent_engine.py``). UI / persistence / API layers should only see
these models, never libtorrent types directly (PLAN §8).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class TorrentState(StrEnum):
    """Torq-owned torrent states (PLAN §7.2).

    The string values are the stable wire representation persisted in
    SQLite and returned over the daemon API.
    """

    METADATA = "metadata"
    QUEUED = "queued"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    STALLED_DOWNLOAD = "stalled_download"
    PAUSED = "paused"
    COMPLETED = "completed"
    SEEDING = "seeding"
    STALLED_UPLOAD = "stalled_upload"
    ERROR = "error"
    REMOVED = "removed"


class SourceType(StrEnum):
    """How a torrent was added."""

    MAGNET = "magnet"
    TORRENT_FILE = "torrent_file"
    TORRENT_URL = "torrent_url"


@dataclass(frozen=True)
class TorrentRef:
    """Stable application reference returned at add time.

    ``id`` is the primary key Torq uses everywhere — for v1 torrents it is
    the SHA-1 info hash; for v2 torrents it is the SHA-256 info hash. When
    both hashes are known (hybrid torrents) the v1 hash is the primary
    ``id`` and the v2 hash is recorded separately.
    """

    id: str
    info_hash_v1: str | None
    info_hash_v2: str | None


@dataclass(frozen=True)
class TorrentFile:
    """A single file inside a (possibly multi-file) torrent."""

    index: int
    path: str  # relative to the torrent root
    size_bytes: int
    priority: int = 4  # see ``priorities.FilePriority``


@dataclass(frozen=True)
class AddOptions:
    """Caller-supplied options when adding a torrent."""

    save_path: Path
    start_paused: bool = False
    sequential: bool = False
    category: str | None = None
    file_priorities: tuple[tuple[int, int], ...] = ()  # (file_index, priority)


@dataclass(frozen=True)
class TransferLimits:
    """Transfer rate limits. ``0`` means unlimited."""

    download_bytes_per_second: int = 0
    upload_bytes_per_second: int = 0


@dataclass
class TorrentStatus:
    """Frequently-returned snapshot of a torrent.

    This is the lightweight shape returned by ``engine.status`` and
    ``engine.list``. Mutations are allowed because the engine rebuilds the
    object on every poll rather than tracking deltas.
    """

    id: str
    name: str
    state: TorrentState
    progress: float  # 0.0 .. 1.0
    total_size: int | None
    downloaded: int
    uploaded: int
    download_rate: int  # bytes/s
    upload_rate: int
    seeds: int
    peers: int
    ratio: float
    eta_seconds: int | None
    queue_position: int | None
    error_message: str | None = None


@dataclass
class Torrent:
    """Full torrent record used by repositories — not the engine hot path."""

    id: str
    name: str
    source_type: SourceType
    source: str | None
    save_path: Path
    state: TorrentState
    progress: float
    total_size: int | None
    downloaded: int
    uploaded: int
    download_rate: int
    upload_rate: int
    seeds: int
    peers: int
    ratio: float
    eta_seconds: int | None
    added_at: datetime
    completed_at: datetime | None = None
    queue_position: int | None = None
    error_message: str | None = None
