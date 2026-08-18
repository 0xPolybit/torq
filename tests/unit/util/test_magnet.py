"""Unit tests for the magnet parser."""

from __future__ import annotations

import base64
import string

import pytest

from torq.errors import InvalidMagnetError
from torq.util.magnet import is_valid_magnet, parse_magnet

# A canonical 40-char hex info hash used across tests.
HEX_HASH = "4d68447ca5b4147459e4be6b44389efb8177c2fb"
HEX_HASH_UPPER = HEX_HASH.upper()
BASE32_HASH = base64.b32encode(bytes.fromhex(HEX_HASH)).decode("ascii")
BTMH_HASH = "1220" + "f" * 64  # placeholder v2 hash (32 bytes hex-encoded)


def _well_formed_magnet() -> str:
    return (
        "magnet:?xt=urn:btih:" + HEX_HASH
        + "&dn=debian-12.5.0-amd64-netinst.iso"
        + "&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"
        + "&tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A6969%2Fannounce"
        + "&ws=http%3A%2F%2Fexample.invalid%2Fseed"
    )


def test_parses_well_formed_magnet() -> None:
    magnet = parse_magnet(_well_formed_magnet())
    assert magnet.info_hash_v1 == HEX_HASH
    assert magnet.display_name == "debian-12.5.0-amd64-netinst.iso"
    assert len(magnet.trackers) == 2
    assert magnet.trackers[0].startswith("udp://")
    assert magnet.trackers[1].startswith("udp://")
    assert len(magnet.web_seeds) == 1


def test_trackers_preserve_order() -> None:
    uri = "magnet:?xt=urn:btih:" + HEX_HASH + "&tr=a&tr=b&tr=c"
    magnet = parse_magnet(uri)
    assert magnet.trackers == ("a", "b", "c")


def test_url_decoded_display_name() -> None:
    uri = "magnet:?xt=urn:btih:" + HEX_HASH + "&dn=hello%20world%21"
    magnet = parse_magnet(uri)
    assert magnet.display_name == "hello world!"


def test_uppercase_hex_is_lowercased() -> None:
    uri = "magnet:?xt=urn:btih:" + HEX_HASH_UPPER
    magnet = parse_magnet(uri)
    assert magnet.info_hash_v1 == HEX_HASH


def test_base32_btih_is_decoded_to_hex() -> None:
    uri = "magnet:?xt=urn:btih:" + BASE32_HASH
    magnet = parse_magnet(uri)
    assert magnet.info_hash_v1 == HEX_HASH


def test_xt_indexed_form_supported() -> None:
    uri = (
        "magnet:?xt.1=urn:btih:" + HEX_HASH
        + "&xt.2=urn:btmh:" + BTMH_HASH.lstrip("1220")  # 64-char placeholder
        + "&dn=hybrid"
    )
    # Provide an actual 64-hex btmh:
    btmh = "f" * 64
    uri = "magnet:?xt.1=urn:btih:" + HEX_HASH + "&xt.2=urn:btmh:" + btmh + "&dn=hybrid"
    magnet = parse_magnet(uri)
    assert magnet.info_hash_v1 == HEX_HASH
    assert magnet.info_hash_v2 == btmh


def test_primary_id_falls_back_from_v1_to_v2() -> None:
    magnet = parse_magnet("magnet:?xt=urn:btmh:" + "f" * 64)
    assert magnet.info_hash_v1 is None
    assert magnet.info_hash_v2 == "f" * 64
    assert magnet.primary_id == "f" * 64


def test_primary_id_prefers_v1() -> None:
    magnet = parse_magnet("magnet:?xt=urn:btih:" + HEX_HASH + "&xt=urn:btmh:" + "f" * 64)
    assert magnet.info_hash_v1 == HEX_HASH
    assert magnet.primary_id == HEX_HASH


def test_xs_and_as_are_captured() -> None:
    uri = (
        "magnet:?xt=urn:btih:" + HEX_HASH
        + "&xs=http%3A%2F%2Fexample.invalid%2F.torrent"
        + "&as=http%3A%2F%2Ffallback.invalid%2F.torrent"
    )
    magnet = parse_magnet(uri)
    assert magnet.exact_source == "http://example.invalid/.torrent"
    assert magnet.acceptable_source == "http://fallback.invalid/.torrent"


def test_unknown_parameters_are_ignored() -> None:
    uri = "magnet:?xt=urn:btih:" + HEX_HASH + "&unknown=value&foo=bar"
    magnet = parse_magnet(uri)
    assert magnet.info_hash_v1 == HEX_HASH


def test_empty_pairs_are_tolerated() -> None:
    uri = "magnet:?xt=urn:btih:" + HEX_HASH + "&&&dn=test"
    magnet = parse_magnet(uri)
    assert magnet.display_name == "test"


@pytest.mark.parametrize(
    "uri",
    [
        "",
        "magnet:",
        "magnet:?",
        "http://example.com/foo",
        "urn:btih:" + HEX_HASH,
    ],
)
def test_rejects_malformed_prefix(uri: str) -> None:
    with pytest.raises(InvalidMagnetError):
        parse_magnet(uri)


def test_rejects_missing_xt() -> None:
    with pytest.raises(InvalidMagnetError):
        parse_magnet("magnet:?dn=nothing")


def test_rejects_pair_without_equals() -> None:
    with pytest.raises(InvalidMagnetError):
        parse_magnet("magnet:?xt=urn:btih:" + HEX_HASH + "&broken")


def test_rejects_invalid_btih_length() -> None:
    with pytest.raises(InvalidMagnetError):
        parse_magnet("magnet:?xt=urn:btih:tooshort")


def test_rejects_btih_with_invalid_hex() -> None:
    bad = "Z" * 40
    with pytest.raises(InvalidMagnetError):
        parse_magnet("magnet:?xt=urn:btih:" + bad)


def test_rejects_btih_with_invalid_base32() -> None:
    bad = "!" * 32
    with pytest.raises(InvalidMagnetError):
        parse_magnet("magnet:?xt=urn:btih:" + bad)


def test_rejects_btmh_wrong_length() -> None:
    with pytest.raises(InvalidMagnetError):
        parse_magnet("magnet:?xt=urn:btmh:" + "f" * 60)


def test_rejects_unknown_urn_scheme() -> None:
    """A magnet with no btih/btmh in xt is rejected even if xt is present."""
    with pytest.raises(InvalidMagnetError):
        parse_magnet("magnet:?xt=urn:nosuchscheme:" + "a" * 40)


def test_invalid_magnet_carries_uri() -> None:
    try:
        parse_magnet("not-a-magnet")
    except InvalidMagnetError as exc:
        assert exc.uri == "not-a-magnet"


def test_is_valid_magnet_returns_false_on_error() -> None:
    assert is_valid_magnet("not-a-magnet") is False
    assert is_valid_magnet("magnet:?dn=nothing") is False
    assert is_valid_magnet("magnet:?xt=urn:btih:" + "Z" * 40) is False


def test_is_valid_magnet_returns_true_for_good_input() -> None:
    assert is_valid_magnet(_well_formed_magnet()) is True


@pytest.mark.parametrize(
    "c",
    list(string.ascii_uppercase.replace("A", "").replace("B", "").replace("C", "").replace("D", "").replace("E", "").replace("F", "")),
)
def test_is_hex_rejects_non_hex_uppercase(c: str) -> None:
    """Hex uppercase characters outside A-F must not be accepted."""
    bad = HEX_HASH[:39] + c
    with pytest.raises(InvalidMagnetError):
        parse_magnet("magnet:?xt=urn:btih:" + bad)
