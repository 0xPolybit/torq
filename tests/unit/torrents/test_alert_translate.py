"""Unit tests for libtorrent alert → Torq event translation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from torq.events.types import (
    FileCompleted,
    FileError,
    TorrentError,
    TorrentMetadataReceived,
    TorrentPaused,
)
from torq.torrents import alerts


def _fake_handle() -> Any:
    return SimpleNamespace()


def _fake_torrent_info(name: str = "x.bin", total_size: int = 1024) -> Any:
    class _Info:
        def name(self_inner: object) -> str:  # noqa: N805
            return name

        def total_size(self_inner: object) -> int:  # noqa: N805
            return total_size

    return _Info()


def _make_alert(name: str, **attrs: Any) -> Any:
    """Construct an alert instance whose ``type.__name__`` is ``name``."""
    cls = type(name, (), {})
    instance = cls()
    for k, v in attrs.items():
        setattr(instance, k, v)
    return instance


def test_torrent_finished_alert_produces_finished_event() -> None:
    handle = _fake_handle()
    alert = _make_alert("torrent_finished_alert", handle=handle, timestamp=None)
    events = alerts.translate(alert, {"abc": handle})
    assert len(events) == 1
    assert events[0].kind == "TorrentFinished"
    assert events[0].torrent_id == "abc"


def test_metadata_received_alert_includes_name_and_size() -> None:
    handle = SimpleNamespace(torrent_file=lambda: _fake_torrent_info("a.bin", 4096))
    alert = _make_alert("metadata_received_alert", handle=handle, timestamp=None)
    events = alerts.translate(alert, {"abc": handle})
    assert len(events) == 1
    assert isinstance(events[0], TorrentMetadataReceived)
    assert events[0].name == "a.bin"
    assert events[0].total_size == 4096


def test_torrent_error_alert_extracts_message() -> None:
    class _Err:
        def value(self) -> int:
            return 1

        def message(self) -> str:
            return "boom"

    handle = _fake_handle()
    alert = _make_alert("torrent_error_alert", handle=handle, error=_Err(), timestamp=None)
    events = alerts.translate(alert, {"abc": handle})
    assert len(events) == 1
    assert isinstance(events[0], TorrentError)
    assert events[0].message == "boom"


def test_torrent_paused_alert() -> None:
    handle = _fake_handle()
    alert = _make_alert("torrent_paused_alert", handle=handle, timestamp=None)
    events = alerts.translate(alert, {"abc": handle})
    assert len(events) == 1
    assert isinstance(events[0], TorrentPaused)


def test_torrent_resumed_alert() -> None:
    handle = _fake_handle()
    alert = _make_alert("torrent_resumed_alert", handle=handle, timestamp=None)
    events = alerts.translate(alert, {"abc": handle})
    assert len(events) == 1
    assert events[0].kind == "TorrentResumed"


def test_torrent_removed_alert() -> None:
    handle = _fake_handle()
    alert = _make_alert("torrent_removed_alert", handle=handle, timestamp=None)
    events = alerts.translate(alert, {"abc": handle})
    assert len(events) == 1
    assert events[0].kind == "TorrentRemoved"


def test_file_completed_alert_includes_index() -> None:
    handle = _fake_handle()
    alert = _make_alert("file_completed_alert", handle=handle, index=3, timestamp=None)
    events = alerts.translate(alert, {"abc": handle})
    assert len(events) == 1
    assert isinstance(events[0], FileCompleted)
    assert events[0].file_index == 3


def test_file_error_alert_includes_message() -> None:
    class _Err:
        def value(self) -> int:
            return 1

        def message(self) -> str:
            return "read failed"

    handle = _fake_handle()
    alert = _make_alert("file_error_alert", handle=handle, index=2, error=_Err(), timestamp=None)
    events = alerts.translate(alert, {"abc": handle})
    assert len(events) == 1
    assert isinstance(events[0], FileError)
    assert events[0].file_index == 2
    assert events[0].message == "read failed"


def test_unknown_alert_returns_empty_list() -> None:
    alert = _make_alert("some_other_alert", handle=_fake_handle(), timestamp=None)
    assert alerts.translate(alert, {"abc": _fake_handle()}) == []


def test_alert_without_handle_returns_empty() -> None:
    alert = _make_alert("torrent_finished_alert", handle=None, timestamp=None)
    assert alerts.translate(alert, {"abc": _fake_handle()}) == []


def test_handle_lookup_uses_inverse_dict() -> None:
    handle = _fake_handle()
    alert = _make_alert("torrent_finished_alert", handle=handle, timestamp=None)
    events = alerts.translate(alert, {"id-1": handle, "id-2": _fake_handle()})
    assert events[0].torrent_id == "id-1"


def test_handle_lookup_falls_back_to_info_hash() -> None:
    handle = SimpleNamespace(
        status=lambda: SimpleNamespace(info_hash="fingerprint"),
    )
    alert = _make_alert("torrent_finished_alert", handle=handle, timestamp=None)
    events = alerts.translate(alert, {})
    assert events[0].torrent_id == "fingerprint"


def test_alert_handles_top_level_exception_in_status() -> None:
    def _boom() -> None:
        msg = "nope"
        raise RuntimeError(msg)

    handle = SimpleNamespace(status=_boom)
    alert = _make_alert("torrent_finished_alert", handle=handle, timestamp=None)
    events = alerts.translate(alert, {})
    assert events[0].torrent_id == ""
