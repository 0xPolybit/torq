"""Torq event types (PLAN §22).

These are the events that the engine translates libtorrent alerts into
and that the daemon's SSE endpoint (slice 0.18) emits to clients.

All events are dataclasses with a stable JSON-friendly shape: ``kind``
identifies the type discriminator, ``torrent_id`` references the
affected torrent, and ``timestamp`` is the wall-clock time of the
event. Per-event kinds add their own fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, kw_only=True)
class TorqEvent:
    """Base event. ``kind`` is the type discriminator on the wire."""

    torrent_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def kind(self) -> str:
        return type(self).__name__

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict for the SSE endpoint."""
        out: dict[str, Any] = {
            "kind": self.kind,
            "torrent_id": self.torrent_id,
            "timestamp": self.timestamp.isoformat(),
        }
        for f in self.__dataclass_fields__:
            if f in out:
                continue
            value = getattr(self, f)
            if isinstance(value, datetime):
                out[f] = value.isoformat()
            else:
                out[f] = value
        return out


@dataclass(frozen=True)
class TorrentAdded(TorqEvent):
    """A torrent was added to the engine."""


@dataclass(frozen=True)
class TorrentMetadataReceived(TorqEvent):
    """Magnet metadata finished downloading."""

    name: str
    total_size: int


@dataclass(frozen=True)
class TorrentFinished(TorqEvent):
    """A torrent finished downloading."""


@dataclass(frozen=True)
class TorrentError(TorqEvent):
    """A torrent entered an error state."""

    message: str


@dataclass(frozen=True)
class TorrentPaused(TorqEvent):
    """A torrent was paused."""


@dataclass(frozen=True)
class TorrentResumed(TorqEvent):
    """A torrent was resumed."""


@dataclass(frozen=True)
class TorrentRemoved(TorqEvent):
    """A torrent was removed from the engine."""


@dataclass(frozen=True)
class FileCompleted(TorqEvent):
    """A file inside a torrent finished downloading."""

    file_index: int


@dataclass(frozen=True)
class FileError(TorqEvent):
    """A file encountered an error."""

    file_index: int
    message: str
