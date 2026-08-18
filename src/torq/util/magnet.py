"""Parse and validate magnet URIs (BEP-9 / PLAN §23).

    Torq parses magnets itself before handing them to libtorrent so the
    application can validate input, extract metadata for display, and return
    clean errors instead of raw engine exceptions.

    Supported parameters
    --------------------
    - ``xt`` (exact topic) — single or ``xt.1``, ``xt.2`` indexed form.
      Recognised URN schemes:
        * ``urn:btih:<40-hex>`` (BitTorrent v1, SHA-1)
        * ``urn:btih:<32-base32>`` (BitTorrent v1 base32 form)
        * ``urn:btmh:<64-hex>`` (BitTorrent v2, SHA-256, multihash prefix 1220)
    - ``dn`` — display name (URL-decoded).
    - ``tr`` — tracker URL (repeatable).
    - ``ws`` — web seed URL (repeatable).
    - ``xs`` — exact source.
    - ``as`` — acceptable source.

    Unknown parameters are ignored (forward compatibility).
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from urllib.parse import unquote

from torq.errors import InvalidMagnetError

_BTIH_HEX_LEN = 40
_BTIH_BASE32_LEN = 32
_BTMH_HEX_LEN = 64


@dataclass(frozen=True)
class Magnet:
    """Parsed magnet URI."""

    raw: str
    info_hash_v1: str | None  # 40 hex chars, lowercased
    info_hash_v2: str | None  # 64 hex chars, lowercased
    display_name: str | None
    trackers: tuple[str, ...]
    web_seeds: tuple[str, ...]
    exact_source: str | None
    acceptable_source: str | None

    @property
    def primary_id(self) -> str:
        """Stable application id: v1 hash if present, else v2, else empty."""
        return self.info_hash_v1 or self.info_hash_v2 or ""


def is_valid_magnet(uri: str) -> bool:
    """Return True iff :func:`parse_magnet` accepts ``uri``."""
    try:
        parse_magnet(uri)
    except InvalidMagnetError:
        return False
    return True


def parse_magnet(uri: str) -> Magnet:
    """Parse a magnet URI.

    Raises:
        InvalidMagnetError: when the URI is empty, malformed, or lacks a
            recognised ``xt`` parameter.
    """
    if not uri:
        raise InvalidMagnetError("empty", uri=uri)
    if not uri.startswith("magnet:?"):
        raise InvalidMagnetError("missing 'magnet:?' prefix", uri=uri)

    query = uri[len("magnet:?") :]

    xt_values: list[str] = []
    trackers: list[str] = []
    web_seeds: list[str] = []
    display_name: str | None = None
    exact_source: str | None = None
    acceptable_source: str | None = None

    for pair in query.split("&"):
        if not pair:
            continue
        if "=" not in pair:
            raise InvalidMagnetError(f"missing '=' in {pair!r}", uri=uri)
        key, _, value = pair.partition("=")
        key = unquote(key)
        value = unquote(value)
        if not key:
            raise InvalidMagnetError(f"empty key in {pair!r}", uri=uri)

        if key == "xt" or key.startswith("xt."):
            xt_values.append(value)
        elif key == "tr":
            trackers.append(value)
        elif key == "ws":
            web_seeds.append(value)
        elif key == "dn":
            display_name = value
        elif key == "xs":
            exact_source = value
        elif key == "as":
            acceptable_source = value
        # Unknown keys: silently ignored for forward compatibility.

    if not xt_values:
        raise InvalidMagnetError("no xt (exact topic) parameter", uri=uri)

    info_hash_v1: str | None = None
    info_hash_v2: str | None = None
    for xt in xt_values:
        if xt.startswith("urn:btih:"):
            info_hash_v1 = _normalize_btih(xt[len("urn:btih:") :], uri=uri)
        elif xt.startswith("urn:btmh:"):
            info_hash_v2 = _normalize_btmh(xt[len("urn:btmh:") :], uri=uri)
        # Other URN schemes are ignored.

    if info_hash_v1 is None and info_hash_v2 is None:
        raise InvalidMagnetError("no btih or btmh in xt parameter", uri=uri)

    return Magnet(
        raw=uri,
        info_hash_v1=info_hash_v1,
        info_hash_v2=info_hash_v2,
        display_name=display_name,
        trackers=tuple(trackers),
        web_seeds=tuple(web_seeds),
        exact_source=exact_source,
        acceptable_source=acceptable_source,
    )


def _normalize_btih(value: str, *, uri: str) -> str:
    """Return a 40-character lowercase hex representation of a v1 info hash."""
    if len(value) == _BTIH_HEX_LEN and _is_hex(value):
        return value.lower()
    if len(value) == _BTIH_BASE32_LEN:
        try:
            decoded = base64.b32decode(value.upper())
        except (binascii.Error, ValueError) as exc:
            raise InvalidMagnetError(f"invalid base32 btih: {exc}", uri=uri) from exc
        if len(decoded) * 2 != _BTIH_HEX_LEN:
            raise InvalidMagnetError(
                f"base32 btih decodes to {len(decoded)} bytes, expected 20",
                uri=uri,
            )
        return decoded.hex()
    raise InvalidMagnetError(
        f"btih must be {_BTIH_HEX_LEN} hex or {_BTIH_BASE32_LEN} base32 chars, got {len(value)}",
        uri=uri,
    )


def _normalize_btmh(value: str, *, uri: str) -> str:
    """Return a 64-character lowercase hex representation of a v2 info hash."""
    if len(value) != _BTMH_HEX_LEN:
        raise InvalidMagnetError(
            f"btmh must be {_BTMH_HEX_LEN} hex chars, got {len(value)}",
            uri=uri,
        )
    if not _is_hex(value):
        raise InvalidMagnetError("btmh contains non-hex characters", uri=uri)
    return value.lower()


def _is_hex(value: str) -> bool:
    return all(c in "0123456789abcdefABCDEF" for c in value)