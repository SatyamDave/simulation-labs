"""In-process sliding-window rate limiting + an IP-keyed FastAPI dependency.

SEC-B (auth hardening). The limiter keeps per-key hit timestamps in memory, so
counters are **per-process**: two uvicorn workers (or two instances behind a
load balancer) each enforce the budget independently. That is fine for the
single-process dev/demo deployment; for a multi-instance production rollout,
back ``RateLimiter`` with a shared store (Redis ``INCR`` + ``EXPIRE``, or a
sorted-set sliding window). The public surface here — ``RateLimiter`` and
``limit_by_ip`` — is designed to stay identical when that swap happens.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Awaitable, Callable, Deque, Dict, Optional

from fastapi import HTTPException, Request


class RateLimiter:
    """Sliding-window counter keyed on an arbitrary string.

    Admits at most ``max`` hits per ``per_seconds`` window per key. Thread-safe
    (a lock guards the per-key deques) so it behaves correctly under the
    threaded ``TestClient`` and uvicorn's worker threads. Expired timestamps are
    evicted lazily on each :meth:`allow` call, so idle keys cost nothing to keep.
    """

    def __init__(self, max: int, per_seconds: float) -> None:
        if max < 1:
            raise ValueError("max must be >= 1")
        if per_seconds <= 0:
            raise ValueError("per_seconds must be > 0")
        self.max = int(max)
        self.per_seconds = float(per_seconds)
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _now(self) -> float:
        # Monotonic clock: immune to wall-clock adjustments (NTP, DST).
        return time.monotonic()

    def allow(self, key: str) -> bool:
        """Record a hit for ``key`` and return True if within budget.

        When the key is already at its limit for the current window, the hit is
        **not** recorded and False is returned (so a blocked client cannot push
        its own window forward by hammering the endpoint).
        """
        now = self._now()
        cutoff = now - self.per_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.max:
                return False
            bucket.append(now)
            return True

    def retry_after(self, key: str) -> float:
        """Seconds until ``key`` frees up a slot (0 if it has budget now)."""
        now = self._now()
        cutoff = now - self.per_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) < self.max:
                return 0.0
            return max(0.0, bucket[0] + self.per_seconds - now)

    def reset(self, key: Optional[str] = None) -> None:
        """Drop recorded hits for one key, or all keys when ``key`` is None."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


def client_ip(request: Request) -> str:
    """Best-effort client IP.

    Trusts the **first** hop of ``X-Forwarded-For`` (the original client as seen
    by the outermost proxy) when present, else the socket peer. Returns
    ``"unknown"`` if neither is available so keying never crashes.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",", 1)[0].strip()
        if first:
            return first
    client = request.client
    if client and client.host:
        return client.host
    return "unknown"


def limit_by_ip(
    bucket: str, max: int, per_seconds: float
) -> Callable[[Request], Awaitable[None]]:
    """Build an async FastAPI dependency enforcing a per-IP sliding window.

    Each call creates its own :class:`RateLimiter`, so different endpoints have
    independent budgets. The ``bucket`` name namespaces the key (handy if a
    limiter is ever shared). Raises ``HTTPException(429)`` with a ``Retry-After``
    header when the caller's IP exceeds ``max`` hits per ``per_seconds``.

    Usage (the orchestrator wires this onto login/signup)::

        @router.post("/login", dependencies=[Depends(limit_by_ip("login", 5, 60))])
    """
    limiter = RateLimiter(max, per_seconds)

    async def _dependency(request: Request) -> None:
        key = f"{bucket}:{client_ip(request)}"
        if not limiter.allow(key):
            retry = int(limiter.retry_after(key)) or 1
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(retry)},
            )

    # Expose the limiter for tests/ops (e.g. reset between test cases).
    _dependency.limiter = limiter  # type: ignore[attr-defined]
    return _dependency


__all__ = ["RateLimiter", "client_ip", "limit_by_ip"]
