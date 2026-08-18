"""Unit tests for the in-process :class:`EventBus`."""

from __future__ import annotations

import asyncio

from torq.events.bus import EventBus
from torq.events.types import TorrentFinished, TorrentPaused


def _event(torrent_id: str = "abc") -> TorrentFinished:
    return TorrentFinished(torrent_id=torrent_id)


async def test_publish_delivers_to_subscribers() -> None:
    bus = EventBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()
    bus.publish(_event("one"))
    assert (await q1.get()).torrent_id == "one"
    assert (await q2.get()).torrent_id == "one"


async def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    q = bus.subscribe()
    bus.unsubscribe(q)
    bus.publish(_event("one"))
    assert q.empty()
    assert bus.subscriber_count == 0


async def test_slow_subscriber_does_not_block_publisher() -> None:
    bus = EventBus(queue_size=2)
    slow = bus.subscribe()
    # Publishing must not block: the subscriber's queue is full
    # but the publisher keeps going.
    for i in range(5):
        bus.publish(_event(f"t{i}"))
    # The queue holds at most 2 — the slowest two would be t0 and t1?
    # No — drop-newest semantics keeps the *first* two events.
    drained = _drain(slow)
    assert len(drained) == 2
    assert [e.torrent_id for e in drained] == ["t0", "t1"]


def _drain(q: asyncio.Queue) -> list[TorrentFinished]:
    out: list[TorrentFinished] = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def test_event_to_dict_has_kind_and_torrent_id() -> None:
    event = TorrentPaused(torrent_id="zzz")
    data = event.to_dict()
    assert data["kind"] == "TorrentPaused"
    assert data["torrent_id"] == "zzz"
    assert "timestamp" in data


def test_event_subclass_serialization_includes_fields() -> None:
    from torq.events.types import FileError

    event = FileError(torrent_id="zzz", file_index=2, message="boom")
    data = event.to_dict()
    assert data["file_index"] == 2
    assert data["message"] == "boom"


def test_event_default_timestamp_is_now() -> None:
    event = TorrentFinished(torrent_id="zzz")
    assert event.timestamp.tzinfo is not None


async def test_subscribe_after_publish_does_not_see_old_events() -> None:
    bus = EventBus()
    bus.publish(_event("late"))
    q = bus.subscribe()
    assert q.empty()


async def test_publish_handles_multiple_events() -> None:
    bus = EventBus()
    q = bus.subscribe()
    for i in range(3):
        bus.publish(_event(f"t{i}"))
    out = [await q.get() for _ in range(3)]
    assert [e.torrent_id for e in out] == ["t0", "t1", "t2"]


async def test_publish_with_no_subscribers_is_noop() -> None:
    bus = EventBus()
    # Should not raise.
    bus.publish(_event("x"))


async def test_event_bus_is_reusable_after_unsubscribe() -> None:
    bus = EventBus()
    q1 = bus.subscribe()
    bus.unsubscribe(q1)
    q2 = bus.subscribe()
    bus.publish(_event("new"))
    assert (await q2.get()).torrent_id == "new"
    assert q1.empty()
