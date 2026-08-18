"""libtorrent alert → :class:`TorqEvent` translation.

libtorrent posts alerts to a session queue (``session.pop_alerts()``).
This module inspects each alert and produces the corresponding Torq
events. The mapping is deliberately narrow: we only translate alerts
that the daemon, TUI, or API actually consume.

The translator uses alert ``type.__name__`` matching so it works
without the libtorrent stub pack and against any current libtorrent
2.x build. Alerts we don't recognise are skipped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from torq.events.types import (
    FileCompleted,
    FileError,
    TorrentAdded,
    TorrentError,
    TorrentFinished,
    TorrentMetadataReceived,
    TorrentPaused,
    TorrentRemoved,
    TorrentResumed,
)

AlertInput = Any  # libtorrent.alert instance
Result = list[Any]  # list[TorqEvent]


def _handle_id(handle: Any, handles: dict[str, Any]) -> str:
    """Resolve a libtorrent handle back to its Torq primary id."""
    for torrent_id, candidate in handles.items():
        if candidate is handle:
            return torrent_id
    # Fall back: try to derive info hash from the handle.
    try:
        info_hash = getattr(handle.status(), "info_hash", None)
        if info_hash is not None:
            return str(info_hash)
    except Exception:
        pass
    return ""


def _timestamp_from_alert(alert: Any) -> datetime:
    """Extract the alert's timestamp when present, otherwise now."""
    ts = getattr(alert, "timestamp", None)
    if isinstance(ts, datetime):
        return ts
    return datetime.now(UTC)


def translate(alert: Any, handles: dict[str, Any]) -> Result:
    """Convert a libtorrent alert into zero or more Torq events."""
    name = type(alert).__name__
    timestamp = _timestamp_from_alert(alert)
    handle = getattr(alert, "handle", None)

    if name == "torrent_added_alert" and handle is not None:
        return [TorrentAdded(torrent_id=_handle_id(handle, handles), timestamp=timestamp)]

    if name == "metadata_received_alert" and handle is not None:
        name_str = ""
        total_size = 0
        try:
            ti = handle.torrent_file()
            if ti is not None:
                name_str = str(ti.name())
                total_size = int(ti.total_size())
        except Exception:
            pass
        return [
            TorrentMetadataReceived(
                torrent_id=_handle_id(handle, handles),
                timestamp=timestamp,
                name=name_str,
                total_size=total_size,
            )
        ]

    if name == "torrent_finished_alert" and handle is not None:
        return [TorrentFinished(torrent_id=_handle_id(handle, handles), timestamp=timestamp)]

    if name == "torrent_error_alert" and handle is not None:
        msg = ""
        try:
            err = getattr(alert, "error", None)
            if err is not None and err.value():
                msg = str(err.message())
        except Exception:
            pass
        return [
            TorrentError(
                torrent_id=_handle_id(handle, handles),
                timestamp=timestamp,
                message=msg,
            )
        ]

    if name == "torrent_paused_alert" and handle is not None:
        return [TorrentPaused(torrent_id=_handle_id(handle, handles), timestamp=timestamp)]

    if name == "torrent_resumed_alert" and handle is not None:
        return [TorrentResumed(torrent_id=_handle_id(handle, handles), timestamp=timestamp)]

    if name == "torrent_removed_alert" and handle is not None:
        return [TorrentRemoved(torrent_id=_handle_id(handle, handles), timestamp=timestamp)]

    if name == "file_completed_alert" and handle is not None:
        return [
            FileCompleted(
                torrent_id=_handle_id(handle, handles),
                timestamp=timestamp,
                file_index=int(getattr(alert, "index", 0) or 0),
            )
        ]

    if name == "file_error_alert" and handle is not None:
        msg = ""
        try:
            err = getattr(alert, "error", None)
            if err is not None and err.value():
                msg = str(err.message())
        except Exception:
            pass
        return [
            FileError(
                torrent_id=_handle_id(handle, handles),
                timestamp=timestamp,
                file_index=int(getattr(alert, "index", 0) or 0),
                message=msg,
            )
        ]

    return []
