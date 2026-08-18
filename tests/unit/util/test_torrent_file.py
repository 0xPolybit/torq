"""Unit tests for the ``.torrent`` metadata parser."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest

from torq.errors import InvalidTorrentFileError
from torq.util.bencode import bencode
from torq.util.torrent_file import MAX_TORRENT_FILE_SIZE, parse_torrent_file

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "torrents"
PAYLOAD_PATH = FIXTURES / "torq-test-payload.bin"
TORRENT_PATH = FIXTURES / "torq-test-payload.bin.torrent"


def _write_torrent(
    tmp_path: Path,
    *,
    info_overrides: dict[bytes, object] | None = None,
) -> Path:
    """Write a minimal single-file v1 .torrent to a temp path."""
    payload = PAYLOAD_PATH.read_bytes()
    info: dict[bytes, object] = {
        b"name": b"custom.bin",
        b"length": len(payload),
        b"piece length": 16 * 1024,
        b"pieces": hashlib.sha1(payload).digest(),
    }
    if info_overrides:
        info.update(info_overrides)
    torrent: dict[bytes, object] = {
        b"announce": b"udp://tracker.example.invalid:80",
        b"info": info,
    }
    target = tmp_path / "custom.torrent"
    target.write_bytes(bencode(torrent))
    return target


def test_parses_fixture_torrent() -> None:
    meta = parse_torrent_file(TORRENT_PATH)
    assert meta.name == "torq-test-payload.bin"
    assert meta.total_size == 4 * 1024
    assert meta.piece_length == 16 * 1024
    assert meta.num_pieces == 1
    assert meta.info_hash_v1 is not None
    assert len(meta.info_hash_v1) == 40
    assert meta.info_hash_v2 is None
    assert meta.announce == "udp://tracker.example.invalid:80"


def test_parses_fixture_files_list() -> None:
    meta = parse_torrent_file(TORRENT_PATH)
    assert len(meta.files) == 1
    assert meta.files[0].path == "torq-test-payload.bin"
    assert meta.files[0].size_bytes == 4 * 1024


def test_info_hash_v1_matches_sha1_of_bencoded_info() -> None:
    """v1 info_hash must equal SHA-1 of the bencoded info dict."""
    from torq.util.bencode import bdecode

    meta = parse_torrent_file(TORRENT_PATH)
    decoded = bdecode(TORRENT_PATH.read_bytes())
    info_dict = decoded[b"info"]
    expected = hashlib.sha1(bencode(info_dict)).hexdigest()
    assert meta.info_hash_v1 == expected


def test_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InvalidTorrentFileError):
        parse_torrent_file(tmp_path / "nope.torrent")


def test_rejects_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.torrent"
    empty.write_bytes(b"")
    with pytest.raises(InvalidTorrentFileError):
        parse_torrent_file(empty)


def test_rejects_oversized_file(tmp_path: Path) -> None:
    big = tmp_path / "big.torrent"
    big.write_bytes(b"\x00" * (MAX_TORRENT_FILE_SIZE + 1))
    with pytest.raises(InvalidTorrentFileError):
        parse_torrent_file(big)


def test_rejects_invalid_bencode(tmp_path: Path) -> None:
    bad = tmp_path / "bad.torrent"
    bad.write_bytes(b"not bencoded data")
    with pytest.raises(InvalidTorrentFileError):
        parse_torrent_file(bad)


def test_rejects_missing_info(tmp_path: Path) -> None:
    bad = tmp_path / "noinfo.torrent"
    bad.write_bytes(bencode({b"announce": b"udp://x"}))
    with pytest.raises(InvalidTorrentFileError):
        parse_torrent_file(bad)


def test_rejects_pieces_length_not_multiple_of_20(tmp_path: Path) -> None:
    bad = _write_torrent(tmp_path, info_overrides={b"pieces": b"\x00" * 19})
    with pytest.raises(InvalidTorrentFileError):
        parse_torrent_file(bad)


def test_rejects_piece_count_mismatch(tmp_path: Path) -> None:
    # 4 KiB payload at 16 KiB piece length = 1 piece, but we give 2 hashes.
    bad = _write_torrent(tmp_path, info_overrides={b"pieces": b"\x00" * 40})
    with pytest.raises(InvalidTorrentFileError):
        parse_torrent_file(bad)


def test_rejects_negative_length(tmp_path: Path) -> None:
    bad = _write_torrent(tmp_path, info_overrides={b"length": -1})
    with pytest.raises(InvalidTorrentFileError):
        parse_torrent_file(bad)


def test_parses_multi_file_v1(tmp_path: Path) -> None:
    """Multi-file v1 torrents enumerate each file."""
    payload = PAYLOAD_PATH.read_bytes()
    sha1 = hashlib.sha1(payload).digest()
    info: dict[bytes, object] = {
        b"name": b"collection",
        b"piece length": 100,  # 300 bytes total → 3 pieces
        b"pieces": sha1 * 3,
        b"files": [
            {b"length": 100, b"path": [b"a", b"one.bin"]},
            {b"length": 200, b"path": [b"b", b"two.bin"]},
        ],
    }
    target = tmp_path / "multi.torrent"
    target.write_bytes(bencode({b"announce": b"udp://x", b"info": info}))

    meta = parse_torrent_file(target)
    assert len(meta.files) == 2
    assert meta.files[0].path == "a/one.bin"
    assert meta.files[0].size_bytes == 100
    assert meta.files[1].path == "b/two.bin"
    assert meta.files[1].size_bytes == 200
    assert meta.total_size == 300


def test_extracts_announce_list(tmp_path: Path) -> None:
    payload = PAYLOAD_PATH.read_bytes()
    info: dict[bytes, object] = {
        b"name": b"x.bin",
        b"length": len(payload),
        b"piece length": 16 * 1024,
        b"pieces": hashlib.sha1(payload).digest(),
    }
    target = tmp_path / "with_list.torrent"
    target.write_bytes(
        bencode(
            {
                b"announce": b"udp://primary.example/announce",
                b"announce-list": [
                    [b"udp://primary.example/announce"],
                    [b"udp://backup1.example/announce", b"udp://backup2.example/announce"],
                ],
                b"info": info,
            }
        )
    )
    meta = parse_torrent_file(target)
    assert meta.announce == "udp://primary.example/announce"
    assert meta.announce_list == (
        "udp://primary.example/announce",
        "udp://backup1.example/announce",
        "udp://backup2.example/announce",
    )


def test_pure_v2_raises_with_clear_message(tmp_path: Path) -> None:
    """Pure v2 torrents (no v1 pieces) currently raise — slice 0.7 limitation."""
    info: dict[bytes, object] = {
        b"name": b"v2-only.bin",
        b"piece length": 16 * 1024,
        b"meta version": 2,
        b"file tree": {b"": {b"": {b"length": 100}}},
    }
    target = tmp_path / "v2.torrent"
    target.write_bytes(bencode({b"info": info}))
    with pytest.raises(InvalidTorrentFileError, match="v2 file-tree"):
        parse_torrent_file(target)