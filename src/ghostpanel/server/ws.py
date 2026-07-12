"""Live event fan-out over WebSockets.

- ``WebSocketHub`` keeps, per ``run_id``, (a) a ring buffer of every event emitted
  so a client that joins mid-run (or after it finishes) replays the backlog, and
  (b) a set of per-subscriber asyncio queues it pushes new events onto.
- ``WebSocketEventSink`` is the concrete ``EventSink`` (frozen Protocol) the runner
  pushes into: ``emit(event)`` serializes the ``RunEvent`` to JSON and publishes it
  to the hub. Safe under ``asyncio.gather`` (every op is synchronous on the event
  loop thread — no ``await`` between mutating shared state).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from typing import Any, Deque

from pydantic import BaseModel


class WebSocketHub:
    """Per-run pub/sub with a replay buffer for late joiners."""

    def __init__(self, buffer_size: int = 2000) -> None:
        self._buffer_size = buffer_size
        self._buffers: dict[str, Deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=buffer_size)
        )
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    async def publish(self, run_id: str, event: dict[str, Any]) -> None:
        """Buffer an event and fan it out to every live subscriber of ``run_id``."""
        self._buffers[run_id].append(event)
        for queue in list(self._subscribers.get(run_id, ())):
            queue.put_nowait(event)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        """Register a subscriber; the returned queue is pre-loaded with the backlog."""
        queue: asyncio.Queue = asyncio.Queue()
        for event in self._buffers.get(run_id, ()):
            queue.put_nowait(event)
        self._subscribers[run_id].add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(run_id)
        if subs is not None:
            subs.discard(queue)

    def buffer(self, run_id: str) -> list[dict[str, Any]]:
        """A snapshot copy of the buffered events for ``run_id`` (for tests/replay)."""
        return list(self._buffers.get(run_id, ()))


class WebSocketEventSink:
    """Concrete ``EventSink`` (registry) — fans a ``RunEvent`` out to WS clients.

    ``event`` is any ``RunEvent`` member (a pydantic model); it is serialized with
    ``model_dump(mode="json")`` so bytes never reach the wire and enums become
    strings — exactly the JSON the frontend renders.
    """

    def __init__(self, run_id: str, hub: WebSocketHub) -> None:
        self.run_id = run_id
        self.hub = hub

    async def emit(self, event: BaseModel) -> None:
        await self.hub.publish(self.run_id, event.model_dump(mode="json"))
