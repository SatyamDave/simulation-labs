"""Live event fan-out: WebSocketHub + WebSocketEventSink (registry EventSink).

The hub keeps, per run, a ring buffer of every event payload published so far
and a set of subscribed websocket-like clients. A client that connects mid-run
gets the backlog replayed (in order, atomically w.r.t. new publishes) before it
starts receiving live events. All hub state is guarded by one asyncio.Lock so
many personas may publish concurrently via `asyncio.gather`.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, Protocol

from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_BUFFER_SIZE = 2000


class _WebSocketLike(Protocol):
    """The only surface the hub needs from a client (FastAPI WebSocket fits)."""

    async def send_json(self, data: Any) -> None: ...


class WebSocketHub:
    """Per-run pub/sub with a replayable ring buffer for late subscribers."""

    def __init__(self, buffer_size: int = DEFAULT_BUFFER_SIZE) -> None:
        self._buffer_size = buffer_size
        self._buffers: dict[str, deque[dict[str, Any]]] = {}
        self._subscribers: dict[str, set[_WebSocketLike]] = {}
        self._lock = asyncio.Lock()

    def buffer(self, run_id: str) -> list[dict[str, Any]]:
        """Snapshot of the event backlog for a run (oldest first)."""
        return list(self._buffers.get(run_id, ()))

    async def subscribe(self, run_id: str, websocket: _WebSocketLike) -> None:
        """Replay the backlog to `websocket`, then register it for live events.

        Replay + registration happen under the hub lock, so no event can be
        missed or delivered out of order around the subscription boundary.
        """
        async with self._lock:
            for payload in self._buffers.get(run_id, ()):
                await websocket.send_json(payload)
            self._subscribers.setdefault(run_id, set()).add(websocket)

    async def unsubscribe(self, run_id: str, websocket: _WebSocketLike) -> None:
        async with self._lock:
            self._subscribers.get(run_id, set()).discard(websocket)

    async def publish(self, run_id: str, payload: dict[str, Any]) -> None:
        """Buffer `payload` and fan it out to all live subscribers of the run.

        Dead sockets (send raises) are dropped silently — a disconnect must
        never break a persona's session loop.
        """
        async with self._lock:
            self._buffers.setdefault(run_id, deque(maxlen=self._buffer_size)).append(payload)
            dead: list[_WebSocketLike] = []
            for ws in self._subscribers.get(run_id, ()):
                try:
                    await ws.send_json(payload)
                except Exception:  # noqa: BLE001 — any send failure means "gone"
                    dead.append(ws)
            for ws in dead:
                self._subscribers[run_id].discard(ws)


class WebSocketEventSink:
    """EventSink (frozen contract) that publishes RunEvents to a WebSocketHub.

    `emit` serializes with `model_dump(mode="json")` so the payload on the wire
    is exactly the discriminated-union JSON the frontend renders.
    """

    def __init__(self, run_id: str, hub: WebSocketHub) -> None:
        self.run_id = run_id
        self.hub = hub

    async def emit(self, event: BaseModel) -> None:
        await self.hub.publish(self.run_id, event.model_dump(mode="json"))
