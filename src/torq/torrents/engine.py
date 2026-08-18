"""TorrentEngine protocol — the boundary between Torq and the engine.

The shape mirrors PLAN §8. Any backend (libtorrent, fake, future
replacement) implements this Protocol and can be plugged into the rest of
Torq without modification.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from torq.torrents.models import (
    AddOptions,
    TorrentRef,
    TorrentStatus,
    TransferLimits,
)


class TorrentEngine(Protocol):
    """Engine interface used by Torq's service / daemon layers."""

    async def start(self) -> None:
        """Initialize the engine (session, defaults)."""

    async def stop(self) -> None:
        """Shut the engine down, persisting any state it owns."""

    async def add_magnet(self, magnet: str, options: AddOptions) -> TorrentRef:
        """Add a magnet URI and return a stable reference."""

    async def add_torrent_file(self, path: Path, options: AddOptions) -> TorrentRef:
        """Add a local ``.torrent`` file and return a stable reference."""

    async def pause(self, torrent_id: str) -> None:
        """Pause a torrent. Idempotent."""

    async def resume(self, torrent_id: str) -> None:
        """Resume a paused torrent. Idempotent."""

    async def remove(self, torrent_id: str, delete_data: bool = False) -> None:
        """Remove a torrent. When ``delete_data`` is true, also delete files."""

    async def recheck(self, torrent_id: str) -> None:
        """Force a re-check of a torrent's piece hashes."""

    async def status(self, torrent_id: str) -> TorrentStatus:
        """Return a snapshot of one torrent's status."""

    async def list(self) -> list[TorrentStatus]:
        """Return a snapshot of every torrent known to the engine."""

    async def set_file_priority(self, torrent_id: str, file_index: int, priority: int) -> None:
        """Set the priority of a single file inside a torrent."""

    async def set_limits(self, torrent_id: str, limits: TransferLimits) -> None:
        """Set per-torrent rate limits."""

    async def set_global_limits(self, limits: TransferLimits) -> None:
        """Set session-wide rate limits."""

    def export_resume(self) -> list:
        """Return a snapshot of resume entries to persist across restarts.

        Engines that do not own persistent state may return ``[]``.
        """
        raise NotImplementedError
