"""Parse and validate ``.torrent`` metadata files (BEP-3, PLAN §25).

Path safety and full v2 file-tree parsing are addressed in later slices.
This module covers:

- file existence + size cap;
- bencode validity;
- v1 / v2 / hybrid info-hash computation;
- single-file and multi-file (v1) torrent file enumeration;
- announce / announce-list extraction;
- piece-count consistency with total size.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from torq.errors import InvalidTorrentFileError
from torq.util.bencode import BencodeDecodeError, bdecode, bencode

MAX_TORRENT_FILE_SIZE = 10 * 1024 * 1024  # 10 MiB


@dataclass(frozen=True)
class TorrentFileEntry:
    """One file inside a (possibly multi-file) torrent."""

    index: int
    path: str  # '/' joined relative path
    size_bytes: int


@dataclass(frozen=True)
class TorrentMetadata:
    """Validated torrent metadata."""

    info_hash_v1: str | None  # 40-char hex, lowercase; None for v2-only
    info_hash_v2: str | None  # 64-char hex, lowercase; None for v1-only
    name: str
    piece_length: int
    num_pieces: int
    total_size: int
    files: tuple[TorrentFileEntry, ...]
    announce: str | None
    announce_list: tuple[str, ...]


def parse_torrent_file(
    path: Path,
    *,
    max_size: int = MAX_TORRENT_FILE_SIZE,
) -> TorrentMetadata:
    """Parse a ``.torrent`` file and return validated metadata.

    Raises:
        InvalidTorrentFileError: when the file is missing, oversized,
            malformed, or structurally invalid.
    """
    if not path.exists():
        raise InvalidTorrentFileError(f"file does not exist: {path}")
    size = path.stat().st_size
    if size == 0:
        raise InvalidTorrentFileError("file is empty")
    if size > max_size:
        raise InvalidTorrentFileError(f"file too large: {size} bytes (max {max_size})")

    data = path.read_bytes()

    try:
        decoded = bdecode(data)
    except BencodeDecodeError as exc:
        raise InvalidTorrentFileError(f"not valid bencode: {exc}") from exc

    if not isinstance(decoded, dict):
        raise InvalidTorrentFileError("top-level must be a dict")

    info = decoded.get(b"info")
    if not isinstance(info, dict):
        raise InvalidTorrentFileError("info dict missing or wrong type")

    info_bytes = bencode(info)
    has_pieces = b"pieces" in info
    is_v2 = b"meta version" in info or b"file tree" in info

    info_hash_v1: str | None = None
    info_hash_v2: str | None = None
    if has_pieces:
        info_hash_v1 = hashlib.sha1(info_bytes).hexdigest()
    if is_v2:
        # BEP-52: v2 hash is SHA-256 of bencoded info with 'pieces' removed.
        info_for_v2 = {k: v for k, v in info.items() if k != b"pieces"}
        info_hash_v2 = hashlib.sha256(bencode(info_for_v2)).hexdigest()

    if info_hash_v1 is None and info_hash_v2 is None:
        raise InvalidTorrentFileError("info has neither v1 pieces nor v2 file tree")

    name_bytes = info.get(b"name")
    if not isinstance(name_bytes, bytes):
        raise InvalidTorrentFileError("info.name missing or wrong type")
    name = name_bytes.decode("utf-8", errors="replace")

    piece_length = info.get(b"piece length")
    if not isinstance(piece_length, int) or piece_length <= 0:
        raise InvalidTorrentFileError("info.piece length missing or invalid")

    pieces = info.get(b"pieces")
    pieces_sha1_count = 0
    if isinstance(pieces, bytes):
        if len(pieces) % 20 != 0:
            raise InvalidTorrentFileError("info.pieces length is not a multiple of 20")
        pieces_sha1_count = len(pieces) // 20

    files, total_size = _extract_files(info, name=name, is_v2=is_v2)

    expected_num_pieces = (total_size + piece_length - 1) // piece_length
    if pieces_sha1_count > 0 and pieces_sha1_count != expected_num_pieces:
        raise InvalidTorrentFileError(
            f"piece count mismatch: expected {expected_num_pieces}, got {pieces_sha1_count}"
        )

    announce: str | None = None
    announce_bytes = decoded.get(b"announce")
    if isinstance(announce_bytes, bytes):
        announce = announce_bytes.decode("utf-8", errors="replace")

    announce_list: list[str] = []
    raw_al = decoded.get(b"announce-list")
    if isinstance(raw_al, list):
        for tier in raw_al:
            if not isinstance(tier, list):
                continue
            for url_bytes in tier:
                if isinstance(url_bytes, bytes):
                    announce_list.append(url_bytes.decode("utf-8", errors="replace"))

    return TorrentMetadata(
        info_hash_v1=info_hash_v1,
        info_hash_v2=info_hash_v2,
        name=name,
        piece_length=piece_length,
        num_pieces=expected_num_pieces,
        total_size=total_size,
        files=tuple(files),
        announce=announce,
        announce_list=tuple(announce_list),
    )


def _extract_files(
    info: dict[bytes, object],
    *,
    name: str,
    is_v2: bool,
) -> tuple[list[TorrentFileEntry], int]:
    """Enumerate files from the info dict and return (entries, total_size)."""
    if b"length" in info:
        length = info[b"length"]
        if not isinstance(length, int) or length < 0:
            raise InvalidTorrentFileError("info.length missing or invalid")
        return [TorrentFileEntry(index=0, path=name, size_bytes=length)], length

    if b"files" in info:
        raw_files = info[b"files"]
        if not isinstance(raw_files, list):
            raise InvalidTorrentFileError("info.files must be a list")
        entries: list[TorrentFileEntry] = []
        total = 0
        for idx, file_info in enumerate(raw_files):
            if not isinstance(file_info, dict):
                raise InvalidTorrentFileError(f"info.files[{idx}] must be a dict")
            length = file_info.get(b"length")
            if not isinstance(length, int) or length < 0:
                raise InvalidTorrentFileError(f"info.files[{idx}].length invalid")
            path_list = file_info.get(b"path")
            if not isinstance(path_list, list):
                raise InvalidTorrentFileError(f"info.files[{idx}].path must be a list")
            parts: list[str] = []
            for part in path_list:
                if not isinstance(part, bytes):
                    raise InvalidTorrentFileError(f"info.files[{idx}].path contains non-bytes")
                parts.append(part.decode("utf-8", errors="replace"))
            entries.append(TorrentFileEntry(index=idx, path="/".join(parts), size_bytes=length))
            total += length
        return entries, total

    if is_v2:
        # Full v2 file-tree parsing lands in a later slice.
        raise InvalidTorrentFileError(
            "v2 file-tree parsing not yet implemented (slice 0.7 limitation)"
        )

    raise InvalidTorrentFileError("info has neither 'length' nor 'files'")
