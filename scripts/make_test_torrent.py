"""Slice 0.4 — generate the controlled test-torrent fixture.

Creates a deterministic small payload and the corresponding v1 ``.torrent``
file under ``tests/fixtures/torrents/``. Safe to re-run; the script always
produces identical bytes because the payload content is deterministic
(``bytes(range(256))`` repeated).

The fixture is intentionally small (4 KiB) so it is cheap to commit and to
ship inside the test suite. A single SHA-1 piece is enough to exercise the
libtorrent engine paths we care about in slices 0.5-0.11.

The bencode implementation is imported from ``torq.util.bencode`` so there
is one canonical implementation across the project.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

# Allow running directly via ``python scripts/make_test_torrent.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from torq.util.bencode import bdecode, bencode

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "torrents"
PAYLOAD_NAME = "torq-test-payload.bin"
TORRENT_NAME = "torq-test-payload.bin.torrent"
PAYLOAD_SIZE = 4 * 1024  # 4 KiB
PIECE_LENGTH = 16 * 1024  # 16 KiB (one piece for a 4 KiB payload)
ANNOUNCE = "udp://tracker.example.invalid:80"


def make_payload() -> bytes:
    """Deterministic 4 KiB content — bytes(range(256)) repeated."""
    return bytes(range(256)) * (PAYLOAD_SIZE // 256)


def make_torrent_bytes(payload: bytes) -> bytes:
    """Build a v1 .torrent file payload."""
    pieces = hashlib.sha1(payload).digest()
    info: dict[bytes, Any] = {
        b"name": PAYLOAD_NAME.encode("utf-8"),
        b"length": len(payload),
        b"piece length": PIECE_LENGTH,
        b"pieces": pieces,
    }
    torrent: dict[bytes, Any] = {
        b"announce": ANNOUNCE.encode("utf-8"),
        b"info": info,
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
        raise AssertionError("info dict missing or wrong type")
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
