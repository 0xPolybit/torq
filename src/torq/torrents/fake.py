"""In-memory :class:`FakeEngine` for tests.

The fake is intentionally trivial — it tracks status objects and supports
all engine methods, but does not simulate network activity. Tests that need
realistic state transitions should use the libtorrent engine under the
integration-test marker instead.
"""

from __future__ import annotations

from pathlib import Path

from torq.torrents.engine import TorrentEngine
from torq.torrents.models import (
    AddOptions,
    TorrentRef,
    TorrentState,
    TorrentStatus,
    TransferLimits,
)


class FakeEngine:
    """Minimal engine implementation suitable for unit tests."""

    def __init__(self) -> None:
        self._torrents: dict[str, TorrentStatus] = {}
        self._started: bool = False
        self.global_limits: TransferLimits = TransferLimits()

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False

    async def add_magnet(self, magnet: str, options: AddOptions) -> TorrentRef:
        if not self._started:
            msg = "FakeEngine.add_magnet called before start()"
            raise RuntimeError(msg)
        # Naive info-hash extraction — real parsing lives in torq.util.magnet.
        info_hash = magnet.split("xt=urn:btih:", 1)[-1].split("&", 1)[0]
        ref = TorrentRef(id=info_hash, info_hash_v1=info_hash, info_hash_v2=None)
        self._torrents[ref.id] = TorrentStatus(
            id=ref.id,
            name="fake",
            state=TorrentState.QUEUED,
            progress=0.0,
            total_size=None,
            downloaded=0,
            uploaded=0,
            download_rate=0,
            upload_rate=0,
            seeds=0,
            peers=0,
            ratio=0.0,
            eta_seconds=None,
            queue_position=len(self._torrents) + 1,
        )
        return ref

    async def add_torrent_file(self, path: Path, options: AddOptions) -> TorrentRef:
        # Fake uses the file stem as a synthetic info hash.
        return await self.add_magnet(
            f"magnet:?xt=urn:btih:{path.stem}&dn={path.name}",
            options,
        )

    async def pause(self, torrent_id: str) -> None:
        status = self._require(torrent_id)
        status.state = TorrentState.PAUSED
        status.download_rate = 0
        status.upload_rate = 0

    async def resume(self, torrent_id: str) -> None:
        status = self._require(torrent_id)
        status.state = TorrentState.DOWNLOADING

    async def remove(self, torrent_id: str, delete_data: bool = False) -> None:
        self._torrents.pop(torrent_id, None)

    async def recheck(self, torrent_id: str) -> None:
        self._require(torrent_id)

    async def status(self, torrent_id: str) -> TorrentStatus:
        return self._require(torrent_id)

    async def list(self) -> list[TorrentStatus]:
        return list(self._torrents.values())

    async def set_file_priority(
        self,
        torrent_id: str,
        file_index: int,
        priority: int,
    ) -> None:
        # Fake doesn't track files; just enforce the contract.
        self._require(torrent_id)
        del file_index, priority  # unused in fake

    async def set_limits(self, torrent_id: str, limits: TransferLimits) -> None:
        self._require(torrent_id)
        del limits  # unused in fake

    async def set_global_limits(self, limits: TransferLimits) -> None:
        self.global_limits = limits

    def _require(self, torrent_id: str) -> TorrentStatus:
        try:
            return self._torrents[torrent_id]
        except KeyError as exc:
            msg = f"unknown torrent id: {torrent_id}"
            raise KeyError(msg) from exc


# Help type checkers see that FakeEngine satisfies the Protocol.
_: TorrentEngine = FakeEngine()  # type: ignore[assignment]
