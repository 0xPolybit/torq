"""Tiny HTTP/1.1 request parser used by :mod:`torq.api.server`.

We avoid pulling in a web framework by handling requests at the
bytestream level. The parser:

- reads the request line (method, target, version)
- reads headers until a blank line
- reads the body up to ``Content-Length`` bytes

The parser is intentionally strict about ``Content-Length`` and
refuses chunked transfer-encoding. We bind to loopback, so the
attack surface is small, but we still want to keep the parser
predictable.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from dataclasses import dataclass


class HTTPParseError(ValueError):
    """Raised when the client sent a malformed HTTP request."""


_MAX_HEADERS = 64
_MAX_BODY_BYTES = 16 * 1024 * 1024  # 16 MB
_REQUEST_LINE = re.compile(r"^([A-Z]+)\s+(\S+)\s+HTTP/(\d)\.(\d)\s*$")


@dataclass(frozen=True, kw_only=True)
class HTTPRequest:
    method: str
    target: str
    version: str
    headers: Mapping[str, str]
    body: bytes


def _parse_headers(lines: list[str]) -> Mapping[str, str]:
    headers: dict[str, str] = {}
    for line in lines:
        if len(headers) >= _MAX_HEADERS:
            msg = "too many headers"
            raise HTTPParseError(msg)
        if ":" not in line:
            msg = f"malformed header line: {line!r}"
            raise HTTPParseError(msg)
        name, _, value = line.partition(":")
        name = name.strip()
        value = value.strip()
        if not name:
            msg = "empty header name"
            raise HTTPParseError(msg)
        # Header names are case-insensitive; normalise to title case.
        canonical = name.lower()
        headers[canonical] = value
    return headers


async def read_request(
    reader: asyncio.StreamReader, max_body: int = _MAX_BODY_BYTES
) -> HTTPRequest:
    """Read one HTTP request from ``reader``."""
    request_line = await reader.readline()
    if not request_line:
        msg = "client closed connection before sending a request"
        raise HTTPParseError(msg)
    if len(request_line) > 8 * 1024:
        msg = "request line too long"
        raise HTTPParseError(msg)
    text = request_line.decode("ascii", errors="replace").rstrip("\r\n")
    match = _REQUEST_LINE.match(text)
    if not match:
        msg = f"invalid request line: {text!r}"
        raise HTTPParseError(msg)
    method, target, major, minor = match.groups()
    if major != "1" or minor not in {"0", "1"}:
        msg = f"unsupported HTTP version: {major}.{minor}"
        raise HTTPParseError(msg)

    headers: list[str] = []
    while True:
        line = await reader.readline()
        if not line:
            msg = "unexpected EOF while reading headers"
            raise HTTPParseError(msg)
        if line in (b"\r\n", b"\n", b""):
            break
        if len(line) > 8 * 1024:
            msg = "header line too long"
            raise HTTPParseError(msg)
        headers.append(line.decode("ascii", errors="replace").rstrip("\r\n"))

    parsed_headers = _parse_headers(headers)
    if parsed_headers.get("transfer-encoding", "").lower() == "chunked":
        msg = "chunked transfer-encoding is not supported"
        raise HTTPParseError(msg)

    body = b""
    content_length = parsed_headers.get("content-length")
    if content_length is not None:
        try:
            length = int(content_length)
        except ValueError as exc:
            msg = f"invalid Content-Length: {content_length}"
            raise HTTPParseError(msg) from exc
        if length < 0 or length > max_body:
            msg = f"Content-Length out of range: {length}"
            raise HTTPParseError(msg)
        body = await reader.readexactly(length)

    return HTTPRequest(
        method=method,
        target=target,
        version=f"{major}.{minor}",
        headers=parsed_headers,
        body=body,
    )


def format_response(
    status: int,
    *,
    body: bytes = b"",
    headers: Mapping[str, str] | None = None,
) -> bytes:
    """Build a complete HTTP/1.1 response."""
    reason = _REASONS.get(status, "Unknown")
    head = [f"HTTP/1.1 {status} {reason}\r\n"]
    merged: dict[str, str] = {"Content-Length": str(len(body))}
    if headers:
        for name, value in headers.items():
            merged[name] = value
    for name, value in merged.items():
        head.append(f"{name}: {value}\r\n")
    head.append("\r\n")
    return "".join(head).encode("ascii") + body


_REASONS = {
    200: "OK",
    201: "Created",
    204: "No Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    413: "Payload Too Large",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


def is_loopback_host(host: str | None) -> bool:
    """Return True if ``host`` (from a Host header) is a loopback address."""
    if host is None:
        return False
    hostname = host.lower().strip()
    # IPv6 literal "[::1]:port" — strip the brackets.
    if hostname.startswith("["):
        end = hostname.find("]")
        if end != -1:
            hostname = hostname[1:end]
    else:
        # Strip the optional port (only for non-bracketed hosts).
        hostname = hostname.split(":", 1)[0]
    return hostname in {"localhost", "127.0.0.1", "::1"}
