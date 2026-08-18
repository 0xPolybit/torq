"""Unit tests for the libtorrent-engine guard helpers.

These tests run with or without libtorrent installed. They cover the
``LibtorrentNotAvailableError`` raised by the constructor when libtorrent
is missing, and the defensive behavior of ``_has_flag``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from torq.torrents.libtorrent_engine import (
    _LIBTORRENT_AVAILABLE,
    LibtorrentEngine,
    LibtorrentNotAvailableError,
    _has_flag,
)


def test_engine_constructor_raises_when_libtorrent_missing() -> None:
    """If libtorrent is missing the engine should fail fast."""
    if _LIBTORRENT_AVAILABLE:
        pytest.skip("libtorrent is installed in this environment")
    with pytest.raises(LibtorrentNotAvailableError):
        LibtorrentEngine()


def test_has_flag_returns_false_for_none_flags() -> None:
    class _BareLt:
        pass

    assert _has_flag(SimpleNamespace(flags=None), "paused", _BareLt()) is False


def test_has_flag_returns_false_for_missing_flag_constant() -> None:
    class _BareLt:
        torrent_flags = SimpleNamespace()  # no `paused` attribute

    assert _has_flag(SimpleNamespace(flags=1 << 5), "paused", _BareLt()) is False


def test_has_flag_returns_false_when_lt_lacks_torrent_flags() -> None:
    class _BareLt:
        pass

    assert _has_flag(SimpleNamespace(flags=0xFF), "paused", _BareLt()) is False


def test_has_flag_handles_garbage_status() -> None:
    class _Lt:
        torrent_flags = SimpleNamespace(paused=1 << 1)

    # Object with no ``flags`` attribute at all — getattr returns 0.
    assert _has_flag(object(), "paused", _Lt()) is False
