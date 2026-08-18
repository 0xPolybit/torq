"""HTTP route handlers (PLAN §16).

Routes are async callables. They return a :class:`Response` whose
``body`` is either ``bytes`` (regular request/response) or an
async iterator yielding ``bytes`` chunks (used by the SSE event
stream).

The router is intentionally small: it matches ``(method, path)``
patterns that use a single ``{name}`` capture per path segment.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from torq.api.http import HTTPRequest
from torq.torrents.models import AddOptions, TorrentRef, TorrentStatus

if TYPE_CHECKING:
    from torq.events.bus import EventBus
    from torq.torrents.engine import TorrentEngine


RouteHandler = Callable[[HTTPRequest, Mapping[str, str]], Awaitable["Response"]]
Body = bytes | AsyncIterator[bytes]


@dataclass(frozen=True, kw_only=True)
class Response:
    """The shape returned by every route handler."""

    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: Body = b""


@dataclass(frozen=True, kw_only=True)
class Route:
    method: str
    pattern: str
    regex: re.Pattern[str]
    handler: RouteHandler


class Router:
    """A tiny method+path dispatcher."""

    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add(self, method: str, pattern: str, handler: RouteHandler) -> None:
        compiled = _compile_pattern(pattern)
        self._routes.append(
            Route(
                method=method.upper(),
                pattern=pattern,
                regex=compiled,
                handler=handler,
            )
        )

    def resolve(
        self, method: str, path: str
    ) -> tuple[RouteHandler, Mapping[str, str]] | None:
        for route in self._routes:
            if route.method != method.upper():
                continue
            match = route.regex.match(path)
            if match is None:
                continue
            return route.handler, match.groupdict()
        return None


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    parts: list[str] = ["^"]
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "{":
            end = pattern.find("}", i)
            if end == -1:
                msg = f"unclosed '{{' in route pattern {pattern!r}"
                raise ValueError(msg)
            name = pattern[i + 1 : end]
            if not name or not name.replace("_", "a").isalnum():
                msg = f"invalid capture name {name!r} in pattern {pattern!r}"
                raise ValueError(msg)
            # Group names must start with a letter or underscore.
            if not (name[0].isalpha() or name[0] == "_"):
                msg = f"invalid capture name {name!r} in pattern {pattern!r}"
                raise ValueError(msg)
            parts.append(f"(?P<{name}>[^/]+)")
            i = end + 1
        else:
            parts.append(re.escape(ch))
            i += 1
    parts.append("$")
    try:
        return re.compile("".join(parts))
    except re.error as exc:
        msg = f"invalid route pattern {pattern!r}: {exc}"
        raise ValueError(msg) from exc


def json_response(
    payload: Any,
    *,
    status: int = 200,
    headers: Mapping[str, str] | None = None,
) -> Response:
    body = json.dumps(_serialise(payload), ensure_ascii=False).encode("utf-8")
    merged: dict[str, str] = {"Content-Type": "application/json"}
    if headers:
        merged.update(headers)
    return Response(status=status, headers=merged, body=body)


def empty_response(status: int = 204) -> Response:
    return Response(status=status, body=b"")


def _serialise(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialise(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _serialise(v) for k, v in value.items()}
    return str(value)


def _status_dict(status: TorrentStatus) -> dict[str, Any]:
    return asdict(status)


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def build_router(
    *,
    engine: TorrentEngine,
    event_bus: EventBus,
    authorize: Callable[[HTTPRequest], bool],
) -> Router:
    """Construct the default route table used by the daemon API."""
    router = Router()
    router.add("GET", "/health", _health)
    router.add("GET", "/torrents", _list_torrents(engine))
    router.add("POST", "/torrents", _add_torrent(engine))
    router.add("DELETE", "/torrents/{id}", _remove_torrent(engine))
    router.add("POST", "/torrents/{id}/pause", _pause(engine))
    router.add("POST", "/torrents/{id}/resume", _resume(engine))
    router.add("GET", "/events", _events(event_bus, authorize))
    return router


async def _health(_request: HTTPRequest, _params: Mapping[str, str]) -> Response:
    return json_response({"status": "ok"})


def _list_torrents(
    engine: TorrentEngine,
) -> Callable[[HTTPRequest, Mapping[str, str]], Awaitable[Response]]:
    async def handler(_request: HTTPRequest, _params: Mapping[str, str]) -> Response:
        items = await engine.list()
        return json_response([_status_dict(s) for s in items])

    return handler


def _add_torrent(
    engine: TorrentEngine,
) -> Callable[[HTTPRequest, Mapping[str, str]], Awaitable[Response]]:
    async def handler(request: HTTPRequest, _params: Mapping[str, str]) -> Response:
        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError as exc:
            return json_response({"error": "invalid JSON", "detail": str(exc)}, status=400)
        source = payload.get("source") if isinstance(payload, dict) else None
        if not isinstance(source, str) or not source:
            return json_response({"error": "missing 'source'"}, status=400)
        save_path = payload.get("save_path") if isinstance(payload, dict) else ""
        save_path = save_path if isinstance(save_path, str) else ""
        start_paused = (
            bool(payload.get("start_paused", False)) if isinstance(payload, dict) else False
        )
        options = AddOptions(save_path=Path(save_path), start_paused=start_paused)
        try:
            if source.startswith("magnet:"):
                ref: TorrentRef = await engine.add_magnet(source, options)
            else:
                ref = await engine.add_torrent_file(Path(source), options)
        except (RuntimeError, ValueError, OSError) as exc:
            return json_response(
                {"error": "add failed", "detail": str(exc)}, status=400
            )
        return json_response(
            {
                "id": ref.id,
                "info_hash_v1": ref.info_hash_v1,
                "info_hash_v2": ref.info_hash_v2,
            },
            status=201,
        )

    return handler


def _remove_torrent(
    engine: TorrentEngine,
) -> Callable[[HTTPRequest, Mapping[str, str]], Awaitable[Response]]:
    async def handler(request: HTTPRequest, params: Mapping[str, str]) -> Response:
        torrent_id = params["id"]
        delete_data = _parse_bool(_query_param(request, "delete_data"), default=False)
        await engine.remove(torrent_id, delete_data=delete_data)
        return empty_response(204)

    return handler


def _pause(
    engine: TorrentEngine,
) -> Callable[[HTTPRequest, Mapping[str, str]], Awaitable[Response]]:
    async def handler(_request: HTTPRequest, params: Mapping[str, str]) -> Response:
        await engine.pause(params["id"])
        return empty_response(204)

    return handler


def _resume(
    engine: TorrentEngine,
) -> Callable[[HTTPRequest, Mapping[str, str]], Awaitable[Response]]:
    async def handler(_request: HTTPRequest, params: Mapping[str, str]) -> Response:
        await engine.resume(params["id"])
        return empty_response(204)

    return handler


def _events(
    event_bus: EventBus,
    authorize: Callable[[HTTPRequest], bool],
) -> Callable[[HTTPRequest, Mapping[str, str]], Awaitable[Response]]:
    async def handler(request: HTTPRequest, _params: Mapping[str, str]) -> Response:
        if not authorize(request):
            return json_response({"error": "unauthorized"}, status=401)
        return Response(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "close",
                "X-Accel-Buffering": "no",
            },
            body=_sse_stream(event_bus),
        )

    return handler


async def _sse_stream(event_bus: EventBus) -> AsyncIterator[bytes]:
    """Yield SSE-formatted events until the consumer cancels."""
    queue = event_bus.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_SSE_KEEPALIVE)
            except TimeoutError:
                yield b": keep-alive\n\n"
                continue
            data = json.dumps(_serialise(event), ensure_ascii=False)
            yield f"event: {event_kind(event)}\ndata: {data}\n\n".encode()
    finally:
        event_bus.unsubscribe(queue)


_SSE_KEEPALIVE = 1.0


def event_kind(event: Any) -> str:
    name = type(event).__name__
    if name.endswith("Event"):
        name = name[:-5]
    return name


def _query_param(request: HTTPRequest, name: str) -> str | None:
    """Return a single query parameter value, or None if absent."""
    target = request.target
    if "?" not in target:
        return None
    _, _, query = target.partition("?")
    for part in query.split("&"):
        if "=" in part:
            k, _, v = part.partition("=")
        else:
            k, v = part, ""
        if k == name:
            return v
    return None
