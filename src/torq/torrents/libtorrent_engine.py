"""libtorrent-backed implementation of :class:`TorrentEngine` (PLAN §9).

The libtorrent Python bindings do not ship universal wheels, so the import
is wrapped in a guard: this module loads even when libtorrent is missing,
but constructing :class:`LibtorrentEngine` fails fast with
:class:`LibtorrentNotAvailableError`. This lets unit tests, linters, and
CI runners without libtorrent still import everything else.

Slice 0.8 implements add + status + list. Pause/resume/remove/recheck and
file priority / limits land in slices 0.9 and 0.10.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from torq.torrents.engine import TorrentEngine
from torq.torrents.models import (
    AddOptions,
    TorrentRef,
    TorrentState,
    TorrentStatus,
    TransferLimits,
)
from torq.util.magnet import parse_magnet

try:
    import libtorrent as _lt  # type: ignore[import-not-found]
    _LIBTORRENT_AVAILABLE = True
except ImportError:
    _lt = None
    _LIBTORRENT_AVAILABLE = False


class LibtorrentNotAvailableError(RuntimeError):
    """Raised when libtorrent is required but not installed."""


def _require_libtorrent() -> Any:
    """Return the libtorrent module or raise."""
    if not _LIBTORRENT_AVAILABLE or _lt is None:
        msg = "libtorrent is not installed; see docs/libtorrent-install.md"
        raise LibtorrentNotAvailableError(msg)
    return _lt


def _has_flag(status: Any, flag_name: str, lt: Any) -> bool:
    """Return True if ``status.flags`` has the named ``torrent_flags`` bit set."""
    flags = getattr(status, "flags", 0)
    if not flags:
        return False
    flag_const = getattr(lt, "torrent_flags", None)
    if flag_const is None:
        return False
    flag_value = getattr(flag_const, flag_name, None)
    if flag_value is None:
        return False
    return bool(int(flags) & int(flag_value))


def map_state(status: Any, lt: Any) -> TorrentState:
    """Translate libtorrent's ``torrent_status`` into a Torq :class:`TorrentState`.

    Pure function over (status, lt) so it is testable without a real session.
    """
    if _has_flag(status, "error", lt):
        return TorrentState.ERROR
    if _has_flag(status, "paused", lt) or _has_flag(status, "paused_auto", lt):
        return TorrentState.PAUSED
    if _has_flag(status, "checking_files", lt) or _has_flag(
        status, "checking_resume_data", lt
    ):
        return TorrentState.CHECKING
    if _has_flag(status, "downloading_metadata", lt):
        return TorrentState.METADATA
    if _has_flag(status, "finished", lt):
        if _has_flag(status, "seeding", lt):
            return TorrentState.SEEDING
        return TorrentState.COMPLETED
    if _has_flag(status, "seeding", lt):
        if int(getattr(status, "upload_payload_rate", 0) or 0) == 0:
            return TorrentState.STALLED_UPLOAD
        return TorrentState.SEEDING
    if _has_flag(status, "downloading", lt):
        if int(getattr(status, "download_payload_rate", 0) or 0) == 0:
            return TorrentState.STALLED_DOWNLOAD
        return TorrentState.DOWNLOADING
    return TorrentState.QUEUED


def _safe_name(handle: Any) -> str:
    try:
        if handle.is_valid():
            ti = handle.torrent_file()
            if ti is not None:
                return str(ti.name())
    except Exception:
        pass
    return "(unknown)"


def _safe_info_hash(handle: Any) -> str:
    try:
        s = handle.status()
        info_hash = getattr(s, "info_hash", None)
        return str(info_hash) if info_hash is not None else ""
    except Exception:
        return ""


def _error_message(status: Any) -> str | None:
    err = getattr(status, "error", None)
    if err is None:
        return None
    try:
        if err.value():
            return str(err.message())
    except Exception:
        return None
    return None


def _build_status(handle: Any, lt: Any) -> TorrentStatus:
    s = handle.status()
    progress_raw = float(getattr(s, "progress", 0.0) or 0.0)
    # libtorrent's progress is either 0..1 (older) or 0..1_000_000 (ppm).
    progress = progress_raw / 1_000_000.0 if progress_raw > 1.0 else progress_raw
    total_size = getattr(s, "total_wanted", None)
    total_size_int = int(total_size) if total_size is not None else None
    downloaded = int(getattr(s, "total_done", 0) or 0)
    uploaded = int(getattr(s, "all_time_upload", 0) or 0)
    download_rate = int(getattr(s, "download_rate", 0) or 0)
    upload_rate = int(getattr(s, "upload_rate", 0) or 0)
    seeds = int(getattr(s, "num_seeds", 0) or 0)
    peers = int(getattr(s, "num_peers", 0) or 0)
    ratio = uploaded / downloaded if downloaded > 0 else 0.0
    eta_seconds: int | None = None
    if total_size_int is not None and download_rate > 0:
        remaining = max(0, total_size_int - downloaded)
        if remaining > 0:
            eta_seconds = int(remaining // download_rate)
    return TorrentStatus(
        id=_safe_info_hash(handle),
        name=_safe_name(handle),
        state=map_state(s, lt),
        progress=progress,
        total_size=total_size_int,
        downloaded=downloaded,
        uploaded=uploaded,
        download_rate=download_rate,
        upload_rate=upload_rate,
        seeds=seeds,
        peers=peers,
        ratio=ratio,
        eta_seconds=eta_seconds,
        queue_position=None,
        error_message=_error_message(s),
    )


class LibtorrentEngine:
    """libtorrent-backed implementation of :class:`TorrentEngine`.

    Construction fails fast when libtorrent is missing. All state is kept
    in-process; the daemon (slice 0.15+) is the only intended owner.
    """

    def __init__(self) -> None:
        self._lt = _require_libtorrent()
        self._session: Any = None
        self._handles: dict[str, Any] = {}

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        if self._session is not None:
            return
        session = self._lt.session()
        session.listen_on(6881, 6891)
        session.add_dht_router("router.bittorrent.com", 6881)
        session.add_dht_router("router.utorrent.com", 6881)
        session.add_dht_router("dht.transmissionbt.com", 6881)
        session.start_dht()
        session.start_lsd()
        session.start_upnp()
        session.start_natpmp()
        self._session = session

    async def stop(self) -> None:
        if self._session is not None:
            self._session.pause()
            self._session = None
            self._handles.clear()

    # -- add ---------------------------------------------------------------

    async def add_magnet(self, magnet: str, options: AddOptions) -> TorrentRef:
        if self._session is None:
            msg = "engine not started"
            raise RuntimeError(msg)
        # Pre-validate so callers get a clean InvalidMagnetError.
        parsed = parse_magnet(magnet)  # raises InvalidMagnetError on failure
        params = self._lt.add_torrent_params()
        params.save_path = str(options.save_path)
        params.url = magnet
        handle = self._session.add_torrent(params)
        primary_id = parsed.info_hash_v1 or parsed.info_hash_v2 or ""
        if primary_id:
            self._handles[primary_id] = handle
        return TorrentRef(
            id=primary_id,
            info_hash_v1=parsed.info_hash_v1,
            info_hash_v2=parsed.info_hash_v2,
        )

    async def add_torrent_file(self, path: Path, options: AddOptions) -> TorrentRef:
        if self._session is None:
            msg = "engine not started"
            raise RuntimeError(msg)
        ti = self._lt.torrent_info(str(path))
        params = self._lt.add_torrent_params()
        params.ti = ti
        params.save_path = str(options.save_path)
        handle = self._session.add_torrent(params)
        info_hash_v1 = str(ti.info_hash()) if ti.info_hash() else ""
        if info_hash_v1:
            self._handles[info_hash_v1] = handle
        return TorrentRef(id=info_hash_v1, info_hash_v1=info_hash_v1, info_hash_v2=None)

    # -- status / list -----------------------------------------------------

    async def status(self, torrent_id: str) -> TorrentStatus:
        if self._session is None:
            msg = "engine not started"
            raise RuntimeError(msg)
        handle = self._handles.get(torrent_id)
        if handle is None:
            msg = f"unknown torrent id: {torrent_id}"
            raise KeyError(msg)
        return _build_status(handle, self._lt)

    async def list(self) -> list[TorrentStatus]:
        if self._session is None:
            return []
        return [_build_status(h, self._lt) for h in self._handles.values()]

    # -- slice 0.9+ stubs --------------------------------------------------

    async def pause(self, torrent_id: str) -> None:
        msg = "LibtorrentEngine.pause lands in slice 0.9"
        raise NotImplementedError(msg)

    async def resume(self, torrent_id: str) -> None:
        msg = "LibtorrentEngine.resume lands in slice 0.9"
        raise NotImplementedError(msg)

    async def remove(self, torrent_id: str, delete_data: bool = False) -> None:
        msg = "LibtorrentEngine.remove lands in slice 0.9"
        raise NotImplementedError(msg)

    async def recheck(self, torrent_id: str) -> None:
        msg = "LibtorrentEngine.recheck lands in slice 0.9"
        raise NotImplementedError(msg)

    async def set_file_priority(
        self, torrent_id: str, file_index: int, priority: int
    ) -> None:
        msg = "LibtorrentEngine.set_file_priority lands in slice 0.10"
        raise NotImplementedError(msg)

    async def set_limits(self, torrent_id: str, limits: TransferLimits) -> None:
        msg = "LibtorrentEngine.set_limits lands in slice 0.10"
        raise NotImplementedError(msg)

    async def set_global_limits(self, limits: TransferLimits) -> None:
        msg = "LibtorrentEngine.set_global_limits lands in slice 0.10"
        raise NotImplementedError(msg)


# Help type checkers see that LibtorrentEngine satisfies the Protocol.
# Guarded so the module still imports on machines without libtorrent
# (local unit-test runs, CI lint jobs).
if _LIBTORRENT_AVAILABLE:
    _: TorrentEngine = LibtorrentEngine()
