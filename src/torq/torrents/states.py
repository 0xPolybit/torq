"""Re-export of the torrent state enum for backwards-compatible imports.

    The authoritative definition lives in :mod:`torq.torrents.models`.
    """

from __future__ import annotations

from torq.torrents.models import TorrentState

__all__ = ["TorrentState"]
