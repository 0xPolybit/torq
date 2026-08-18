"""Minimal bencode encoder / decoder used by the torrent metadata parser.

This is a plain-Python implementation so Torq can parse ``.torrent`` files
without depending on libtorrent. The earlier fixture script
(``scripts/make_test_torrent.py``) imports this module so the canonical
implementation lives in one place.
"""

from __future__ import annotations

from typing import Any


class BencodeDecodeError(ValueError):
    """Raised when bencoded data cannot be parsed."""


def bencode(obj: Any) -> bytes:
    """Encode a Python object as bencode.

    Supported types: ``int``, ``bytes``, ``str``, ``list``, ``dict``. Dict
    keys must be ``bytes`` or ``str`` and are emitted in sorted order, as
    required by the bencode specification.
    """
    if isinstance(obj, bool):
        raise TypeError("bool not supported in bencode (encode as int)")
    if isinstance(obj, int):
        return f"i{obj}e".encode()
    if isinstance(obj, bytes):
        return f"{len(obj)}:".encode() + obj
    if isinstance(obj, str):
        encoded = obj.encode("utf-8")
        return f"{len(encoded)}:".encode() + encoded
    if isinstance(obj, list):
        return b"l" + b"".join(bencode(item) for item in obj) + b"e"
    if isinstance(obj, dict):
        out = b"d"
        for key in sorted(obj):
            out += bencode(key) + bencode(obj[key])
        return out + b"e"
    raise TypeError(f"Cannot bencode {type(obj).__name__}")


def bdecode(data: bytes) -> Any:
    """Decode bencoded data into a Python object."""
    cursor = [0]

    def read() -> Any:
        if cursor[0] >= len(data):
            raise BencodeDecodeError("Unexpected end of data")
        c = data[cursor[0]]
        cursor[0] += 1
        if c == ord("i"):
            try:
                end = data.index(b"e", cursor[0])
            except ValueError as exc:
                raise BencodeDecodeError("Unterminated integer") from exc
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
            # Length string starts at cursor[0]-1 (the digit we already
            # consumed), so single-digit lengths still parse correctly.
            digit_start = cursor[0] - 1
            try:
                colon = data.index(b":", digit_start)
            except ValueError as exc:
                raise BencodeDecodeError("Unterminated string") from exc
            try:
                length = int(data[digit_start:colon])
            except ValueError as exc:
                raise BencodeDecodeError(f"Invalid length: {exc}") from exc
            cursor[0] = colon + 1
            start = cursor[0]
            if start + length > len(data):
                raise BencodeDecodeError("String runs past end of data")
            cursor[0] = start + length
            return data[start : start + length]
        raise BencodeDecodeError(f"Unexpected byte 0x{c:02x} at position {cursor[0] - 1}")

    result = read()
    if cursor[0] != len(data):
        raise BencodeDecodeError(f"Trailing data after position {cursor[0]}")
    return result
