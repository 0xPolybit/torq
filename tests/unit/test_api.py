"""Unit tests for the HTTP API."""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path

import pytest

from torq.api import (
    APIServer,
    HTTPParseError,
    HTTPRequest,
    Response,
    Router,
    ServerAddressError,
    ServerConfig,
    TokenStore,
    format_response,
    generate_token,
    is_loopback_host,
    json_response,
    read_request,
    validate_loopback,
    write_token_file,
)
from torq.events.bus import EventBus
from torq.torrents.fake import FakeEngine

# --------------------------------------------------------------------- utils


async def _request(server: APIServer, raw: bytes) -> bytes:
    reader, writer = await asyncio.open_connection(server.host, server.port)
    writer.write(raw)
    await writer.drain()
    response = b""
    while True:
        chunk = await reader.read(4096)
        if not chunk:
            break
        response += chunk
    writer.close()
    await writer.wait_closed()
    return response


def _build_get(path: str = "/health") -> bytes:
    return (
        f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nAccept: */*\r\nConnection: close\r\n\r\n"
    ).encode("ascii")


def _build_post_json(path: str, body: dict[str, object], token: str | None = None) -> bytes:
    encoded = json.dumps(body).encode("utf-8")
    headers = [
        f"POST {path} HTTP/1.1",
        "Host: 127.0.0.1",
        f"Content-Length: {len(encoded)}",
        "Content-Type: application/json",
        "Connection: close",
    ]
    if token is not None:
        headers.append(f"Authorization: Bearer {token}")
    headers.append("")
    headers.append("")
    return ("\r\n".join(headers) + encoded.decode("utf-8")).encode("utf-8")


def _build_delete(path: str, token: str | None = None) -> bytes:
    headers = [
        f"DELETE {path} HTTP/1.1",
        "Host: 127.0.0.1",
        "Connection: close",
    ]
    if token is not None:
        headers.append(f"Authorization: Bearer {token}")
    headers.append("")
    headers.append("")
    return "\r\n".join(headers).encode("utf-8")


def _build_patch_json(path: str, body: dict[str, object], token: str) -> bytes:
    encoded = json.dumps(body).encode("utf-8")
    headers = [
        f"PATCH {path} HTTP/1.1",
        "Host: 127.0.0.1",
        f"Content-Length: {len(encoded)}",
        "Content-Type: application/json",
        f"Authorization: Bearer {token}",
        "Connection: close",
    ]
    headers.append("")
    headers.append("")
    return ("\r\n".join(headers) + encoded.decode("utf-8")).encode("utf-8")


def _status_from_response(raw: bytes) -> int:
    line = raw.split(b"\r\n", 1)[0].decode("ascii")
    return int(line.split(" ")[1])


def _body_from_response(raw: bytes) -> bytes:
    _, _, rest = raw.partition(b"\r\n\r\n")
    return rest


# --------------------------------------------------------------------- tests


def test_validate_loopback_accepts_localhost() -> None:
    assert validate_loopback("localhost") == "127.0.0.1"


def test_validate_loopback_rejects_public_host() -> None:
    with pytest.raises(ServerAddressError):
        validate_loopback("0.0.0.0")  # means "all interfaces" — not loopback-only
    with pytest.raises(ServerAddressError):
        validate_loopback("8.8.8.8")


def test_is_loopback_host_accepts_localhost() -> None:
    assert is_loopback_host("localhost") is True
    assert is_loopback_host("127.0.0.1:8910") is True
    assert is_loopback_host("[::1]:8910") is True


def test_is_loopback_host_rejects_public_host() -> None:
    assert is_loopback_host("example.com") is False
    assert is_loopback_host("10.0.0.1") is False
    assert is_loopback_host(None) is False


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok(tmp_path: Path) -> None:
    engine = FakeEngine()
    await engine.start()
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.start()
    try:
        response = await _request(server, _build_get("/health"))
        assert _status_from_response(response) == 200
        body = json.loads(_body_from_response(response))
        assert body == {"status": "ok"}
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_list_torrents_returns_engine_results(tmp_path: Path) -> None:
    engine = FakeEngine()
    await engine.start()
    ref = await engine.add_magnet(
        "magnet:?xt=urn:btih:abc&dn=demo",
        None,  # type: ignore[arg-type]
    )
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    auth = tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.start()
    try:
        raw = await _request(
            server,
            _build_get(
                "/torrents",
            ),
        )  # type: ignore[arg-type]
        request = _build_get("/torrents")
        del raw, request  # silence unused
        raw = await _request(server, _build_get("/torrents"))
        # Re-issue with auth header.
        raw = await _request(
            server,
            (
                "GET /torrents HTTP/1.1\r\n"
                "Host: 127.0.0.1\r\n"
                f"Authorization: Bearer {auth.token}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode("ascii"),
        )
        assert _status_from_response(raw) == 200
        body = json.loads(_body_from_response(raw))
        assert isinstance(body, list)
        assert any(item["id"] == ref.id for item in body)
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_unauthorized_request_returns_401(tmp_path: Path) -> None:
    engine = FakeEngine()
    await engine.start()
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.start()
    try:
        raw = await _request(server, _build_get("/torrents"))
        assert _status_from_response(raw) == 401
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_invalid_token_returns_401(tmp_path: Path) -> None:
    engine = FakeEngine()
    await engine.start()
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.start()
    try:
        bad = (
            "GET /torrents HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "Authorization: Bearer not-the-real-token\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        raw = await _request(server, bad)
        assert _status_from_response(raw) == 401
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_unknown_route_returns_404(tmp_path: Path) -> None:
    engine = FakeEngine()
    await engine.start()
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.start()
    try:
        raw = await _request(server, _build_get("/nope"))
        assert _status_from_response(raw) == 404
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_non_loopback_host_header_rejected(tmp_path: Path) -> None:
    engine = FakeEngine()
    await engine.start()
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.start()
    try:
        bad = (
            "GET /health HTTP/1.1\r\nHost: evil.example.com\r\nConnection: close\r\n\r\n"
        ).encode("ascii")
        raw = await _request(server, bad)
        assert _status_from_response(raw) == 400
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_add_torrent_with_magnet(tmp_path: Path) -> None:
    engine = FakeEngine()
    await engine.start()
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    auth = tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.start()
    try:
        raw = await _request(
            server,
            _build_post_json(
                "/torrents",
                {"source": "magnet:?xt=urn:btih:abc&dn=demo"},
                token=auth.token,
            ),
        )
        assert _status_from_response(raw) == 201
        body = json.loads(_body_from_response(raw))
        assert body["id"] == "abc"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_add_torrent_with_missing_source_returns_400(tmp_path: Path) -> None:
    engine = FakeEngine()
    await engine.start()
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    auth = tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.start()
    try:
        raw = await _request(
            server,
            _build_post_json("/torrents", {}, token=auth.token),
        )
        assert _status_from_response(raw) == 400
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_pause_resume_remove_round_trip(tmp_path: Path) -> None:
    engine = FakeEngine()
    await engine.start()
    ref = await engine.add_magnet(
        "magnet:?xt=urn:btih:abc&dn=demo",
        None,  # type: ignore[arg-type]
    )
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    auth = tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.start()
    try:
        # Pause
        raw = await _request(
            server,
            _build_post_json(f"/torrents/{ref.id}/pause", {}, token=auth.token),
        )
        assert _status_from_response(raw) == 204
        # Resume
        raw = await _request(
            server,
            _build_post_json(f"/torrents/{ref.id}/resume", {}, token=auth.token),
        )
        assert _status_from_response(raw) == 204
        # Remove
        raw = await _request(
            server,
            _build_delete(f"/torrents/{ref.id}", token=auth.token),
        )
        assert _status_from_response(raw) == 204
        # List should be empty now.
        raw = await _request(
            server,
            (
                "GET /torrents HTTP/1.1\r\n"
                "Host: 127.0.0.1\r\n"
                f"Authorization: Bearer {auth.token}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode("ascii"),
        )
        body = json.loads(_body_from_response(raw))
        assert body == []
    finally:
        await server.stop()


async def _seed_engine(tmp_path: Path) -> tuple[FakeEngine, APIServer, str, str]:
    """Start a server with one torrent seeded and return useful handles."""
    engine = FakeEngine()
    await engine.start()
    ref = await engine.add_magnet(
        "magnet:?xt=urn:btih:abc&dn=demo",
        None,  # type: ignore[arg-type]
    )
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    auth = tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.start()
    return engine, server, ref.id, auth.token


@pytest.mark.asyncio
async def test_get_torrent_returns_status(tmp_path: Path) -> None:
    _engine, server, torrent_id, token = await _seed_engine(tmp_path)
    try:
        request = (
            f"GET /torrents/{torrent_id} HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            f"Authorization: Bearer {token}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        raw = await _request(server, request)
        assert _status_from_response(raw) == 200
        body = json.loads(_body_from_response(raw))
        assert body["id"] == torrent_id
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_get_torrent_unknown_returns_404(tmp_path: Path) -> None:
    _engine, server, _torrent_id, token = await _seed_engine(tmp_path)
    try:
        request = (
            "GET /torrents/nonexistent HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            f"Authorization: Bearer {token}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        raw = await _request(server, request)
        assert _status_from_response(raw) == 404
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_recheck_returns_204(tmp_path: Path) -> None:
    _engine, server, torrent_id, token = await _seed_engine(tmp_path)
    try:
        raw = await _request(
            server, _build_post_json(f"/torrents/{torrent_id}/recheck", {}, token=token)
        )
        assert _status_from_response(raw) == 204
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_recheck_unknown_returns_404(tmp_path: Path) -> None:
    _engine, server, _torrent_id, token = await _seed_engine(tmp_path)
    try:
        raw = await _request(
            server,
            _build_post_json("/torrents/nonexistent/recheck", {}, token=token),
        )
        assert _status_from_response(raw) == 404
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_pause_unknown_returns_404(tmp_path: Path) -> None:
    _engine, server, _torrent_id, token = await _seed_engine(tmp_path)
    try:
        raw = await _request(server, _build_post_json("/torrents/nope/pause", {}, token=token))
        assert _status_from_response(raw) == 404
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_patch_file_priority_accepts_valid_value(tmp_path: Path) -> None:
    _engine, server, torrent_id, token = await _seed_engine(tmp_path)
    try:
        raw = await _request(
            server,
            _build_patch_json(
                f"/torrents/{torrent_id}/files/0",
                {"priority": 5},
                token=token,
            ),
        )
        assert _status_from_response(raw) == 204
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_patch_file_priority_rejects_out_of_range(tmp_path: Path) -> None:
    _engine, server, torrent_id, token = await _seed_engine(tmp_path)
    try:
        raw = await _request(
            server,
            _build_patch_json(
                f"/torrents/{torrent_id}/files/0",
                {"priority": 99},
                token=token,
            ),
        )
        assert _status_from_response(raw) == 400
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_patch_file_priority_rejects_non_integer(tmp_path: Path) -> None:
    _engine, server, torrent_id, token = await _seed_engine(tmp_path)
    try:
        raw = await _request(
            server,
            _build_patch_json(
                f"/torrents/{torrent_id}/files/0",
                {"priority": "high"},
                token=token,
            ),
        )
        assert _status_from_response(raw) == 400
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_patch_file_priority_unknown_torrent_returns_404(tmp_path: Path) -> None:
    _engine, server, _torrent_id, token = await _seed_engine(tmp_path)
    try:
        raw = await _request(
            server,
            _build_patch_json(
                "/torrents/nope/files/0",
                {"priority": 3},
                token=token,
            ),
        )
        assert _status_from_response(raw) == 404
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_patch_limits_accepts_valid_payload(tmp_path: Path) -> None:
    _engine, server, torrent_id, token = await _seed_engine(tmp_path)
    try:
        raw = await _request(
            server,
            _build_patch_json(
                f"/torrents/{torrent_id}/limits",
                {"download_bytes_per_second": 1024, "upload_bytes_per_second": 512},
                token=token,
            ),
        )
        assert _status_from_response(raw) == 204
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_patch_limits_rejects_negative_values(tmp_path: Path) -> None:
    _engine, server, torrent_id, token = await _seed_engine(tmp_path)
    try:
        raw = await _request(
            server,
            _build_patch_json(
                f"/torrents/{torrent_id}/limits",
                {"download_bytes_per_second": -1, "upload_bytes_per_second": 0},
                token=token,
            ),
        )
        assert _status_from_response(raw) == 400
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_patch_limits_rejects_missing_fields(tmp_path: Path) -> None:
    _engine, server, torrent_id, token = await _seed_engine(tmp_path)
    try:
        raw = await _request(
            server,
            _build_patch_json(
                f"/torrents/{torrent_id}/limits",
                {"download_bytes_per_second": 100},
                token=token,
            ),
        )
        assert _status_from_response(raw) == 400
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_patch_limits_unknown_torrent_returns_404(tmp_path: Path) -> None:
    _engine, server, _torrent_id, token = await _seed_engine(tmp_path)
    try:
        raw = await _request(
            server,
            _build_patch_json(
                "/torrents/nope/limits",
                {"download_bytes_per_second": 0, "upload_bytes_per_second": 0},
                token=token,
            ),
        )
        assert _status_from_response(raw) == 404
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_events_endpoint_returns_sse_headers(tmp_path: Path) -> None:
    engine = FakeEngine()
    await engine.start()
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    auth = tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.start()
    try:
        reader, writer = await asyncio.open_connection(server.host, server.port)
        request = (
            "GET /events HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            f"Authorization: Bearer {auth.token}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        writer.write(request)
        await writer.drain()
        # Read the response head.
        head = await reader.readline()
        assert head.startswith(b"HTTP/1.1 200")
        # Read remaining headers + first chunk header to confirm SSE format.
        headers_raw = b""
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            headers_raw += line
        assert b"Content-Type: text/event-stream" in headers_raw
        assert b"Transfer-Encoding: chunked" in headers_raw
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_events_endpoint_rejects_unauthorized(tmp_path: Path) -> None:
    engine = FakeEngine()
    await engine.start()
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.start()
    try:
        raw = await _request(
            server,
            ("GET /events HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n").encode(
                "ascii"
            ),
        )
        assert _status_from_response(raw) == 401
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_server_binds_to_assigned_port(tmp_path: Path) -> None:
    engine = FakeEngine()
    await engine.start()
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.start()
    try:
        assert server.port > 0
        assert server.host == "127.0.0.1"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_server_double_start_fails(tmp_path: Path) -> None:
    """A second server bound to the same fixed port must fail to bind."""
    engine = FakeEngine()
    await engine.start()
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    tokens.provision()
    # First server binds an OS-assigned port.
    s1 = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await s1.start()
    try:
        # Second server uses the same fixed port — must fail.
        s2 = APIServer(
            config=ServerConfig(host="127.0.0.1", port=s1.port),
            engine=engine,
            event_bus=bus,
            tokens=tokens,
        )
        with pytest.raises(OSError):
            await s2.start()
    finally:
        await s1.stop()


@pytest.mark.asyncio
async def test_server_stop_idempotent(tmp_path: Path) -> None:
    engine = FakeEngine()
    await engine.start()
    bus = EventBus()
    tokens = TokenStore(tmp_path / "tok")
    tokens.provision()
    server = APIServer(
        config=ServerConfig(host="127.0.0.1", port=0),
        engine=engine,
        event_bus=bus,
        tokens=tokens,
    )
    await server.stop()  # never started — must not raise
    await server.start()
    await server.stop()
    await server.stop()  # double stop is fine


def test_format_response_includes_content_length() -> None:
    raw = format_response(200, body=b"hello")
    assert b"Content-Length: 5" in raw
    assert raw.endswith(b"hello")


def test_format_response_with_extra_headers() -> None:
    raw = format_response(
        201,
        body=b"",
        headers={"Location": "/x"},
    )
    assert b"201 Created" in raw
    assert b"Location: /x" in raw


@pytest.mark.asyncio
async def test_read_request_parses_simple_get() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"GET /foo HTTP/1.1\r\nHost: x\r\n\r\n")
    reader.feed_eof()
    request = await read_request(reader)
    assert request.method == "GET"
    assert request.target == "/foo"
    assert request.headers["host"] == "x"
    assert request.body == b""


@pytest.mark.asyncio
async def test_read_request_parses_post_body() -> None:
    reader = asyncio.StreamReader()
    body = b'{"a": 1}'
    reader.feed_data(
        f"POST /x HTTP/1.1\r\nHost: y\r\nContent-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    )
    reader.feed_eof()
    request = await read_request(reader)
    assert request.method == "POST"
    assert request.body == body


@pytest.mark.asyncio
async def test_read_request_rejects_negative_content_length() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"POST /x HTTP/1.1\r\nHost: y\r\nContent-Length: -1\r\n\r\n")
    reader.feed_eof()
    with pytest.raises(HTTPParseError):
        await read_request(reader)


@pytest.mark.asyncio
async def test_read_request_rejects_chunked_encoding() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"POST /x HTTP/1.1\r\nHost: y\r\nTransfer-Encoding: chunked\r\n\r\n")
    reader.feed_eof()
    with pytest.raises(HTTPParseError):
        await read_request(reader)


def test_router_resolves_simple_route() -> None:
    async def handler(_req: HTTPRequest, _params: object) -> Response:
        return json_response({"ok": True})

    router = Router()
    router.add("GET", "/foo", handler)
    resolved = router.resolve("GET", "/foo")
    assert resolved is not None


def test_router_returns_none_for_unknown() -> None:
    router = Router()
    assert router.resolve("GET", "/nope") is None


def test_router_returns_none_for_wrong_method() -> None:
    async def handler(_req: HTTPRequest, _params: object) -> Response:
        return json_response({})

    router = Router()
    router.add("GET", "/foo", handler)
    assert router.resolve("POST", "/foo") is None


def test_router_captures_path_parameters() -> None:
    async def handler(_req: HTTPRequest, params: object) -> Response:
        assert isinstance(params, dict)
        return json_response({"id": params["id"]})  # type: ignore[index]

    router = Router()
    router.add("DELETE", "/torrents/{id}", handler)
    resolved = router.resolve("DELETE", "/torrents/abc")
    assert resolved is not None
    _handler_fn, params = resolved
    assert params["id"] == "abc"


def test_router_compile_rejects_invalid_capture_name() -> None:
    router = Router()

    def bad(_req: HTTPRequest, _params: object) -> Response:
        return json_response({})

    with pytest.raises(ValueError):
        router.add("GET", "/{1bad}", bad)  # type: ignore[arg-type]


def test_router_compile_rejects_unclosed_brace() -> None:
    router = Router()

    def bad(_req: HTTPRequest, _params: object) -> Response:
        return json_response({})

    with pytest.raises(ValueError):
        router.add("GET", "/{name", bad)  # type: ignore[arg-type]


def test_json_response_sets_content_type() -> None:
    response = json_response({"k": "v"})
    assert response.headers["Content-Type"] == "application/json"
    assert b'"k": "v"' in response.body  # type: ignore[operator]


def test_json_response_uses_custom_status() -> None:
    response = json_response({"error": "x"}, status=400)
    assert response.status == 400


def test_token_store_provision_writes_file(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tok")
    ctx = store.provision(length=16)
    assert ctx.token_path.exists()
    assert store.current() == ctx.token


def test_token_store_load_reads_existing(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tok")
    store.provision(length=16)
    fresh = TokenStore(tmp_path / "tok")
    ctx = fresh.load()
    assert ctx.token == store.current()


def test_token_store_authorize_accepts_valid_bearer(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tok")
    ctx = store.provision()
    assert store.authorize(f"Bearer {ctx.token}") is True


def test_token_store_authorize_rejects_invalid_bearer(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tok")
    store.provision()
    assert store.authorize("Bearer wrong-token") is False
    assert store.authorize("Basic abc") is False
    assert store.authorize(None) is False


def test_token_store_clear_keeps_disk_file(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tok")
    store.provision()
    path = store.path
    store.clear()
    assert path.exists()  # file remains
    assert store.current() is None


def test_generate_token_produces_unique_tokens() -> None:
    tokens = {generate_token(16) for _ in range(10)}
    assert len(tokens) == 10


def test_write_token_file_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "tok"
    write_token_file(target, "hello")
    assert target.read_text() == "hello"
    assert not (tmp_path / "tok.tmp").exists()
