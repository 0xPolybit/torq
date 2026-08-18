"""Unit tests for the bencode implementation."""

from __future__ import annotations

import pytest

from torq.util.bencode import BencodeDecodeError, bdecode, bencode


def test_round_trip_integer() -> None:
    assert bdecode(bencode(42)) == 42
    assert bdecode(bencode(-1)) == -1
    assert bdecode(bencode(0)) == 0


def test_round_trip_string() -> None:
    assert bdecode(bencode("hello")) == b"hello"
    assert bdecode(bencode("")) == b""


def test_round_trip_bytes() -> None:
    assert bdecode(bencode(b"raw-bytes")) == b"raw-bytes"


def test_round_trip_list() -> None:
    obj = [1, "two", b"three", [4, 5]]
    assert bdecode(bencode(obj)) == [1, b"two", b"three", [4, 5]]


def test_round_trip_dict_keys_are_sorted() -> None:
    obj = {"z": 1, "a": 2, "m": 3}
    encoded = bencode(obj)
    assert bdecode(encoded) == {b"a": 2, b"m": 3, b"z": 1}
    # 'a' must appear before 'm' which must appear before 'z' in the encoding.
    assert encoded.index(b"1:a") < encoded.index(b"1:m") < encoded.index(b"1:z")


def test_rejects_bool() -> None:
    with pytest.raises(TypeError):
        bencode(True)


def test_rejects_unsupported_type() -> None:
    with pytest.raises(TypeError):
        bencode(3.14)


def test_decode_empty_bytes_raises() -> None:
    with pytest.raises(BencodeDecodeError):
        bdecode(b"")


def test_decode_truncated_integer_raises() -> None:
    with pytest.raises(BencodeDecodeError):
        bdecode(b"i12")


def test_decode_truncated_string_raises() -> None:
    with pytest.raises(BencodeDecodeError):
        bdecode(b"5:ab")


def test_decode_invalid_integer_raises() -> None:
    with pytest.raises(BencodeDecodeError):
        bdecode(b"iXYZ e")


def test_decode_unexpected_byte_raises() -> None:
    with pytest.raises(BencodeDecodeError):
        bdecode(b"?")


def test_decode_trailing_data_raises() -> None:
    with pytest.raises(BencodeDecodeError):
        bdecode(b"i1ei2e")


def test_decode_empty_dict_and_list() -> None:
    assert bdecode(b"de") == {}
    assert bdecode(b"le") == []


def test_single_digit_lengths_parse() -> None:
    """Regression: single-digit length strings used to slice empty."""
    obj = b"x"
    assert bdecode(bencode(obj)) == b"x"
