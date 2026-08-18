"""Unit tests for libtorrent → Torq state mapping.

These tests do not require libtorrent to be installed. They construct a
fake ``lt`` module with the flag constants we depend on, plus a fake
``status`` object whose ``flags`` field is set explicitly.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from torq.torrents.libtorrent_engine import map_state
from torq.torrents.models import TorrentState


class _Flags:
    """Stand-in for libtorrent's ``torrent_flags`` constants."""

    error = 1 << 0
    paused = 1 << 1
    queued_for_checking = 1 << 2
    checking_files = 1 << 3
    checking_resume_data = 1 << 4
    downloading_metadata = 1 << 5
    downloading = 1 << 6
    finished = 1 << 7
    seeding = 1 << 8
    paused_auto = 1 << 9


class _Lt:
    torrent_flags = _Flags


def _status(flag_value: int, **extras: Any) -> SimpleNamespace:
    return SimpleNamespace(flags=flag_value, **extras)


def test_error_state_takes_precedence() -> None:
    s = _status(_Flags.error | _Flags.paused | _Flags.downloading)
    assert map_state(s, _Lt()) == TorrentState.ERROR


def test_paused_state() -> None:
    s = _status(_Flags.paused)
    assert map_state(s, _Lt()) == TorrentState.PAUSED


def test_paused_auto_state() -> None:
    s = _status(_Flags.paused_auto)
    assert map_state(s, _Lt()) == TorrentState.PAUSED


def test_checking_files_state() -> None:
    s = _status(_Flags.checking_files)
    assert map_state(s, _Lt()) == TorrentState.CHECKING


def test_checking_resume_data_state() -> None:
    s = _status(_Flags.checking_resume_data)
    assert map_state(s, _Lt()) == TorrentState.CHECKING


def test_metadata_state() -> None:
    s = _status(_Flags.downloading_metadata)
    assert map_state(s, _Lt()) == TorrentState.METADATA


def test_finished_seeding_is_seeding() -> None:
    s = _status(_Flags.finished | _Flags.seeding)
    assert map_state(s, _Lt()) == TorrentState.SEEDING


def test_finished_without_seeding_is_completed() -> None:
    s = _status(_Flags.finished)
    assert map_state(s, _Lt()) == TorrentState.COMPLETED


def test_seeding_with_upload_rate() -> None:
    s = _status(_Flags.seeding, upload_payload_rate=1024)
    assert map_state(s, _Lt()) == TorrentState.SEEDING


def test_seeding_without_upload_rate_is_stalled_upload() -> None:
    s = _status(_Flags.seeding, upload_payload_rate=0)
    assert map_state(s, _Lt()) == TorrentState.STALLED_UPLOAD


def test_downloading_with_rate() -> None:
    s = _status(_Flags.downloading, download_payload_rate=1024)
    assert map_state(s, _Lt()) == TorrentState.DOWNLOADING


def test_downloading_without_rate_is_stalled_download() -> None:
    s = _status(_Flags.downloading, download_payload_rate=0)
    assert map_state(s, _Lt()) == TorrentState.STALLED_DOWNLOAD


def test_no_flags_is_queued() -> None:
    s = _status(0)
    assert map_state(s, _Lt()) == TorrentState.QUEUED


def test_none_flags_is_queued() -> None:
    s = SimpleNamespace(flags=None)
    assert map_state(s, _Lt()) == TorrentState.QUEUED


def test_missing_status_is_queued() -> None:
    assert map_state(None, _Lt()) == TorrentState.QUEUED


def test_missing_flag_constants_default_to_safe() -> None:
    """An lt module without torrent_flags gracefully degrades."""

    class _BareLt:
        pass

    s = _status(_Flags.paused)
    assert map_state(s, _BareLt()) == TorrentState.QUEUED
