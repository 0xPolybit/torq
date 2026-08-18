"""Local HTTP server (PLAN §16).

A loopback-only HTTP/1.1 server that exposes the daemon's API.
It refuses to bind to anything other than ``127.0.0.1`` and
validates the ``Host`` header on incoming requests. Authentication
uses bearer tokens supplied by :mod:`torq.api.auth`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from torq.api.auth import TokenStore
from torq.api.http import (
    HTTPParseError,
    HTTPRequest,
    format_response,
    is_loopback_host,
    read_request,
)
from torq.api.routes import Body, Response, Router, build_router

if TYPE_CHECKING:
    from torq.events.bus import EventBus
    from torq.torrents.engine import TorrentEngine


_LOG = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ServerConfig:
    """Resolved configuration for a server instance."""

    host: str = "127.0.0.1"
    port: int = 8910


class ServerAddressError(RuntimeError):
    """Raised when the configured host is not a loopback address."""


class APIError(Exception):
    """Raised when an API call cannot complete (e.g. during shutdown)."""


def validate_loopback(host: str) -> str:
    """Return ``host`` if it is loopback, otherwise raise ``ServerAddressError``."""
    if not is_loopback_host(host):
        msg = f"API host must be loopback; got {host!r}"
        raise ServerAddressError(msg)
    # Normalise to IPv4 loopback so we always have a concrete bind address.
    return "127.0.0.1"


class APIServer:
    """The HTTP API bound to a single loopback port."""

    def __init__(
        self,
        *,
        config: ServerConfig,
        engine: TorrentEngine,
        event_bus: EventBus,
        tokens: TokenStore,
        router: Router | None = None,
    ) -> None:
        self._config = config
        self._engine = engine
        self._bus = event_bus
        self._tokens = tokens
        self._router = router or build_router(
            engine=engine,
            event_bus=event_bus,
            authorize=self._authorize,
        )
        self._server: asyncio.base_events.Server | None = None
        self._bound_host: str | None = None
        self._bound_port: int | None = None

    @property
    def router(self) -> Router:
        return self._router

    @property
    def port(self) -> int:
        if self._bound_port is None:
            msg = "API server is not running"
            raise APIError(msg)
        return self._bound_port

    @property
    def host(self) -> str:
        if self._bound_host is None:
            msg = "API server is not running"
            raise APIError(msg)
        return self._bound_host

    async def start(self) -> None:
        host = validate_loopback(self._config.host)
        self._server = await asyncio.start_server(
            self._handle_connection, host, self._config.port
        )
        socks = self._server.sockets or ()
        if not socks:
            msg = "API server bound no sockets"
            raise APIError(msg)
        sock = socks[0]
        # The kernel fills in the assigned port when ``port == 0``.
        self._bound_port = sock.getsockname()[1]
        self._bound_host = host

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        with contextlib.suppress(Exception):
            await self._server.wait_closed()
        self._server = None
        self._bound_port = None
        self._bound_host = None

    def _authorize(self, request: HTTPRequest) -> bool:
        header = request.headers.get("authorization")
        return self._tokens.authorize(header)

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        try:
            request = await read_request(reader)
            if not is_loopback_host(request.headers.get("host")):
                await _write_full(
                    writer,
                    format_response(400, headers={"Connection": "close"}),
                )
                return
            if request.target.startswith("/health"):
                # Health checks bypass auth by convention.
                response = await self._dispatch(request, require_auth=False)
            else:
                response = await self._dispatch(request, require_auth=True)
            await _write_response(writer, response)
        except HTTPParseError as exc:
            await _write_full(writer, _bad_request(str(exc)))
            _LOG.warning("malformed request from %s: %s", peer, exc)
        except ConnectionResetError:
            pass
        except Exception:
            _LOG.exception("unhandled error in API connection")
            with contextlib.suppress(Exception):
                await _write_full(writer, _internal_error())
        finally:
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def _dispatch(
        self, request: HTTPRequest, *, require_auth: bool
    ) -> Response:
        # Split path from the query string before matching.
        path = request.target.split("?", 1)[0]
        resolved = self._router.resolve(request.method, path)
        if resolved is None:
            return Response(status=404, body=b'{"error":"not found"}')
        # Auth check happens after routing so unknown paths return 404, not 401.
        if require_auth and not self._authorize(request):
            return Response(
                status=401,
                headers={"WWW-Authenticate": "Bearer"},
                body=b'{"error":"unauthorized"}',
            )
        handler, params = resolved
        try:
            return await handler(request, params)
        except (ValueError, KeyError):
            # Caller-side errors: surface a generic message. Do NOT echo the
            # exception text since handlers may embed sensitive data.
            return Response(
                status=400,
                headers={"Content-Type": "application/json"},
                body=b'{"error":"bad request"}',
            )
        # Anything else is a server fault — fall through to the connection
        # handler, which logs and returns a generic 500.


async def _write_response(
    writer: asyncio.StreamWriter, response: Response
) -> None:
    body = response.body
    if isinstance(body, AsyncIterator):
        await _stream_response(writer, response, body)
        return
    head = format_response(
        response.status,
        body=body if isinstance(body, (bytes, bytearray)) else b"",
        headers=dict(response.headers),
    )
    writer.write(head)
    await writer.drain()


async def _stream_response(
    writer: asyncio.StreamWriter,
    response: Response,
    body: AsyncIterator[bytes],
) -> None:
    """Write an SSE-style response with chunked transfer-encoding."""
    parts = [
        f"HTTP/1.1 {response.status} {_REASONS.get(response.status, 'OK')}\r\n",
        "Transfer-Encoding: chunked\r\n",
    ]
    for name, value in response.headers.items():
        parts.append(f"{name}: {value}\r\n")
    parts.append("\r\n")
    writer.write("".join(parts).encode("ascii"))
    await writer.drain()
    try:
        async for chunk in body:
            if writer.is_closing():
                break
            if not chunk:
                continue
            header = f"{len(chunk):x}\r\n".encode("ascii")
            try:
                writer.write(header)
                writer.write(chunk)
                writer.write(b"\r\n")
                await writer.drain()
            except (ConnectionResetError, BrokenPipeError, OSError):
                break
    finally:
        with contextlib.suppress(ConnectionResetError, BrokenPipeError, OSError):
            writer.write(b"0\r\n\r\n")
            await writer.drain()


_REASONS = {
    200: "OK",
    201: "Created",
    204: "No Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    500: "Internal Server Error",
}


async def _write_full(writer: asyncio.StreamWriter, response_bytes: bytes) -> None:
    writer.write(response_bytes)
    with contextlib.suppress(ConnectionResetError):
        await writer.drain()


def _bad_request(detail: str) -> bytes:
    payload = '{"error":"' + detail.replace('"', '\\"') + '"}'
    return format_response(400, body=payload.encode("utf-8"))


def _internal_error() -> bytes:
    return format_response(500, body=b'{"error":"internal server error"}')


# Re-export Body for callers that want to type-check Response bodies.
__all__ = [
    "APIError",
    "APIServer",
    "Body",
    "Response",
    "Router",
    "ServerAddressError",
    "ServerConfig",
    "validate_loopback",
]


_ = Mapping  # keep the typing import in use
