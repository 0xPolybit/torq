"""In-process event bus (PLAN §22).

A simple pub/sub broker used between the engine (producer) and the
SSE endpoint (consumer). Each subscriber gets its own bounded queue;
slow consumers drop events rather than back-pressure the engine.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torq.events.types import TorqEvent


class EventBus:
    """Bounded-multicast pub/sub for :class:`TorqEvent`."""

    def __init__(self, queue_size: int = 1024) -> None:
        self._subscribers: list[asyncio.Queue[TorqEvent]] = []
        self._queue_size = queue_size
        self._lock = asyncio.Lock()

    def subscribe(self) -> asyncio.Queue[TorqEvent]:
        """Return a new queue that receives every event published from now on."""
        queue: asyncio.Queue[TorqEvent] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[TorqEvent]) -> None:
        """Remove a subscriber. Idempotent."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def publish(self, event: TorqEvent) -> None:
        """Publish an event to every subscriber. Drops for slow consumers.

        The publisher never blocks: if a subscriber's queue is full, the
        event is dropped for that subscriber only. Fast subscribers drain
        their queue, slow subscribers lose the most recent events.
        """
        for queue in self._subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
