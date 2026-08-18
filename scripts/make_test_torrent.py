"""Slice 0.4 — generate the controlled test-torrent fixture.

Creates a deterministic small payload and the corresponding v1 ``.torrent``
file under ``tests/fixtures/torrents/``. Safe to re-run; the script always
produces identical bytes because the payload content is deterministic
(``bytes(range(256))`` repeated).

The fixture is intentionally small (4 KiB) so it is cheap to commit and to
ship inside the test suite. A single SHA-1 piece is enough to exercise the
libtorrent engine paths we care about in slices 0.5-0.11.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "torrents"
PAYLOAD_NAME = "torq-test-payload.bin"
TORRENT_NAME = "torq-test-payload.bin.torrent"
PAYLOAD_SIZE = 4 * 1024  # 4 KiB
PIECE_LENGTH = 16 * 1024  # 16 KiB (one piece for a 4 KiB payload)
ANNOUNCE = "udp://tracker.example.invalid:80"


def bencode(obj: Any) -> bytes:
    """Encode a Python object as bencode."""
    if isinstance(obj, bool):
        raise TypeError("bool not supported in bencode (encode as int)")
    if isinstance(obj, int):
        return f"i{obj}e".encode("utf-8")
    if isinstance(obj, bytes):
        return f"{len(obj)}:".encode("utf-8") + obj
    if isinstance(obj, str):
        encoded = obj.encode("utf-8")
        return f"{len(encoded)}:".encode("utf-8") + encoded
    if isinstance(obj, list):
        return b"l" + b"".join(bencode(item) for item in obj) + b"e"
    if isinstance(obj, dict):
        out = b"d"
        for key in sorted(obj):
            out += bencode(key) + bencode(obj[key])
        return out + b"e"
    raise TypeError(f"Cannot bencode {type(obj).__name__}")


class BencodeDecodeError(ValueError):
    """Raised when bencoded data cannot be parsed."""


def bdecode(data: bytes) -> Any:
    """Decode bencoded data into a Python object."""
    cursor = [0]

    def read() -> Any:
        if cursor[0] >= len(data):
            raise BencodeDecodeError("Unexpected end of data")
        c = data[cursor[0]]
        cursor[0] += 1
        if c == ord("i"):
            end = data.index(b"e", cursor[0])
            try:
                n = int(data[cursor[0] : end])
            except ValueError as exc:
                raise BencodeDecodeError(f"Invalid integer: {exc}") from exc
            cursor[0] = end + 1
            return n
        if c == ord("l"):
            items: list[Any] = []
            while data[cursor[0]] != ord("e"):
                items.append(read())
            cursor[0] += 1
            return items
        if c == ord("d"):
            result: dict[Any, Any] = {}
            while data[cursor[0]] != ord("e"):
                key = read()
                result[key] = read()
            cursor[0] += 1
            return result
        if chr(c).isdigit():
            # Length string starts at cursor[0]-1 (the digit we already consumed),
            # so single-digit lengths still parse correctly.
            digit_start = cursor[0] - 1
            colon = data.index(b":", digit_start)
            try:
                length = int(data[digit_start:colon])
            except ValueError as exc:
                raise BencodeDecodeError(f"Invalid length: {exc}") from exc
            cursor[0] = colon + 1
            start = cursor[0]
            cursor[0] = start + length
            return data[start : start + length]
        raise BencodeDecodeError(f"Unexpected byte 0x{c:02x} at position {cursor[0] - 1}")

    result = read()
    if cursor[0] != len(data):
        raise BencodeDecodeError(f"Trailing data after position {cursor[0]}")
    return result


def make_payload() -> bytes:
    """Deterministic 4 KiB content — bytes(range(256)) repeated."""
    return bytes(range(256)) * (PAYLOAD_SIZE // 256)


def make_torrent_bytes(payload: bytes) -> bytes:
    """Build a v1 .torrent file payload."""
    pieces = hashlib.sha1(payload).digest()
    info: dict[str, Any] = {
        "name": PAYLOAD_NAME,
        "length": len(payload),
        "piece length": PIECE_LENGTH,
        "pieces": pieces,
    }
    torrent: dict[str, Any] = {
        "announce": ANNOUNCE,
        "info": info,
    }
    return bencode(torrent)


def self_verify(torrent_path: Path, payload_path: Path) -> None:
    """Read back the generated fixtures and verify their structure."""
    torrent = bdecode(torrent_path.read_bytes())
    if not isinstance(torrent, dict):
        raise AssertionError(f"Expected dict, got {type(torrent).__name__}")
    if torrent.get(b"announce") != ANNOUNCE.encode("utf-8"):
        raise AssertionError("announce field mismatch")
    info = torrent.get(b"info")
    if not isinstance(info, dict):
        raise AssertionError("info field missing or wrong type")
    if info.get(b"name") != PAYLOAD_NAME.encode("utf-8"):
        raise AssertionError("info.name mismatch")
    if info.get(b"length") != PAYLOAD_SIZE:
        raise AssertionError("info.length mismatch")
    if info.get(b"piece length") != PIECE_LENGTH:
        raise AssertionError("info.piece length mismatch")
    expected_pieces = hashlib.sha1(payload_path.read_bytes()).digest()
    if info.get(b"pieces") != expected_pieces:
        raise AssertionError("info.pieces SHA-1 mismatch")


def main() -> int:
    """Write fixtures under ``tests/fixtures/torrents/`` and self-verify."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    payload = make_payload()
    payload_path = FIXTURES_DIR / PAYLOAD_NAME
    torrent_path = FIXTURES_DIR / TORRENT_NAME
    payload_path.write_bytes(payload)
    torrent_path.write_bytes(make_torrent_bytes(payload))
    print(f"Wrote {payload_path} ({len(payload)} bytes)")
    print(f"Wrote {torrent_path} ({torrent_path.stat().st_size} bytes)")
    self_verify(torrent_path, payload_path)
    print("Self-verify OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())