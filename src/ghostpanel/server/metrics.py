"""SRE observability: a tiny, dependency-free Prometheus ``/metrics`` endpoint.

We hand-roll the Prometheus/OpenMetrics text exposition format on top of the
stdlib (a ``dict`` guarded by a ``threading.Lock``) rather than pulling in
``prometheus_client`` — the surface we need (a couple of labelled counters and
one latency histogram) is small and the format is stable.

Public surface the composition root / other modules use:

  * module-level metrics ``HTTP_REQUESTS``, ``HTTP_LATENCY``, ``RUNS_TOTAL``,
    ``JOBS_TOTAL`` (constructed once at import — import-safe, no I/O);
  * ``inc_run(outcome)`` / ``inc_job(state)`` convenience helpers other modules
    call as runs finish and jobs change state;
  * ``render_prometheus()`` → the full exposition text;
  * ``MetricsMiddleware`` — records every HTTP request's count + latency;
  * ``add_metrics(app)`` — installs the middleware and registers ``GET /metrics``.

Everything is process-local. For a multi-instance deployment each replica
exposes its own ``/metrics`` and Prometheus aggregates by scraping all of them
(note this in ops docs); there is no shared/global store here.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

# Prometheus text format content type (v0.0.4).
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

# Default request-duration buckets (seconds), matching Prometheus client defaults.
_DEFAULT_BUCKETS: tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
)


def _escape_label_value(value: str) -> str:
    """Escape a label value per the exposition format: ``\\`` → ``\\\\``,
    ``"`` → ``\\"``, newline → ``\\n``."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )


def _format_labels(names: Iterable[str], values: Iterable[str]) -> str:
    """Render ``{a="1",b="2"}`` (or ``""`` when there are no labels)."""
    pairs = [
        f'{name}="{_escape_label_value(value)}"'
        for name, value in zip(names, values)
    ]
    if not pairs:
        return ""
    return "{" + ",".join(pairs) + "}"


def _format_float(value: float) -> str:
    """Compact numeric rendering: integers print without a trailing ``.0``."""
    if value == int(value):
        return str(int(value))
    return repr(value)


class Counter:
    """A monotonically increasing counter with a fixed set of label names.

    Thread-safe. ``inc(**labels)`` bumps the series identified by the label
    values; series are created lazily on first touch.
    """

    def __init__(self, name: str, documentation: str, labelnames: tuple[str, ...]):
        self.name = name
        self.documentation = documentation
        self.labelnames = labelnames
        self._values: dict[tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def _key(self, labels: dict[str, str]) -> tuple[str, ...]:
        return tuple(str(labels[n]) for n in self.labelnames)

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = self._key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def collect(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.documentation}",
            f"# TYPE {self.name} counter",
        ]
        with self._lock:
            items = sorted(self._values.items())
        for key, value in items:
            labels = _format_labels(self.labelnames, key)
            lines.append(f"{self.name}{labels} {_format_float(value)}")
        return lines


class Histogram:
    """A cumulative histogram with fixed buckets and a fixed set of label names.

    Each series tracks per-bucket observation counts, a running ``_sum`` and a
    ``_count``. ``_bucket`` lines are emitted cumulatively (``le`` = "less than
    or equal") with a final ``+Inf`` bucket, as the format requires.
    """

    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: tuple[str, ...],
        buckets: tuple[float, ...] = _DEFAULT_BUCKETS,
    ):
        self.name = name
        self.documentation = documentation
        self.labelnames = labelnames
        self.buckets = tuple(buckets)
        # per series: ([count per bucket], sum, count)
        self._values: dict[tuple[str, ...], tuple[list[int], float, int]] = {}
        self._lock = threading.Lock()

    def _key(self, labels: dict[str, str]) -> tuple[str, ...]:
        return tuple(str(labels[n]) for n in self.labelnames)

    def observe(self, value: float, **labels: str) -> None:
        key = self._key(labels)
        with self._lock:
            counts, total, count = self._values.get(
                key, ([0] * len(self.buckets), 0.0, 0)
            )
            for i, upper in enumerate(self.buckets):
                if value <= upper:
                    counts[i] += 1
            self._values[key] = (counts, total + value, count + 1)

    def collect(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.documentation}",
            f"# TYPE {self.name} histogram",
        ]
        with self._lock:
            items = sorted(self._values.items())
        for key, (counts, total, count) in items:
            cumulative = 0
            for i, upper in enumerate(self.buckets):
                cumulative += counts[i]
                le_labels = _format_labels(
                    (*self.labelnames, "le"), (*key, _format_float(upper))
                )
                lines.append(f"{self.name}_bucket{le_labels} {cumulative}")
            inf_labels = _format_labels(
                (*self.labelnames, "le"), (*key, "+Inf")
            )
            lines.append(f"{self.name}_bucket{inf_labels} {count}")
            base_labels = _format_labels(self.labelnames, key)
            lines.append(f"{self.name}_sum{base_labels} {_format_float(total)}")
            lines.append(f"{self.name}_count{base_labels} {count}")
        return lines


# ---------------------------------------------------------------------------
# Module-level metrics (constructed once; import-safe).
# ---------------------------------------------------------------------------
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests, by route path, method and status code.",
    ("path", "method", "status"),
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds, by route path.",
    ("path",),
)
RUNS_TOTAL = Counter(
    "runs_total",
    "Total persona/run outcomes recorded.",
    ("outcome",),
)
JOBS_TOTAL = Counter(
    "jobs_total",
    "Total job state transitions recorded.",
    ("state",),
)

# Registry order controls the exposition order (stable output for scrapers/tests).
_REGISTRY: tuple[Counter | Histogram, ...] = (
    HTTP_REQUESTS,
    HTTP_LATENCY,
    RUNS_TOTAL,
    JOBS_TOTAL,
)


def inc_run(outcome: str) -> None:
    """Increment ``runs_total{outcome=...}``. Accepts an enum or a raw string."""
    RUNS_TOTAL.inc(outcome=getattr(outcome, "value", outcome))


def inc_job(state: str) -> None:
    """Increment ``jobs_total{state=...}``. Accepts an enum or a raw string."""
    JOBS_TOTAL.inc(state=getattr(state, "value", state))


def render_prometheus() -> str:
    """Render the full Prometheus text exposition for all registered metrics."""
    lines: list[str] = []
    for metric in _REGISTRY:
        lines.extend(metric.collect())
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Path normalization — keep label cardinality bounded.
# ---------------------------------------------------------------------------
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_NUMERIC_RE = re.compile(r"^\d+$")
_LONG_HEX_RE = re.compile(r"^[0-9a-fA-F]{16,}$")


def _normalize_segment(segment: str) -> str:
    if _UUID_RE.match(segment) or _NUMERIC_RE.match(segment) or _LONG_HEX_RE.match(segment):
        return ":id"
    return segment


def normalize_path(path: str) -> str:
    """Collapse high-cardinality id segments (numeric / UUID / long hex) to
    ``:id`` so ``/v2/runs/<uuid>`` and ``/v2/runs/<other-uuid>`` share one label.

    A matched route template (``request.scope["route"].path``) is preferred by
    the middleware; this is the fallback for raw paths."""
    if not path:
        return path
    parts = path.split("/")
    return "/".join(_normalize_segment(p) for p in parts)


def _route_template(request: Request) -> str | None:
    """The matched route's template (e.g. ``/v2/runs/{run_id}``) if routing has
    resolved one, else None. Uses only the already-parameterized template so it
    is inherently low-cardinality."""
    route = request.scope.get("route")
    path_format = getattr(route, "path_format", None) or getattr(route, "path", None)
    return path_format if isinstance(path_format, str) else None


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record ``http_requests_total`` and ``http_request_duration_seconds`` for
    every request. Never breaks the response if metric recording fails."""

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001, ANN201
        start = time.perf_counter()
        status = 500
        try:
            response: Response = await call_next(request)
            status = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - start
            try:
                path = _route_template(request) or normalize_path(request.url.path)
                HTTP_REQUESTS.inc(
                    path=path, method=request.method, status=str(status)
                )
                HTTP_LATENCY.observe(elapsed, path=path)
            except Exception:  # noqa: BLE001 - metrics must never break serving
                pass


def add_metrics(app) -> None:  # noqa: ANN001
    """Wire metrics into ``app``: install ``MetricsMiddleware`` and register a
    ``GET /metrics`` endpoint returning the Prometheus text exposition. Called by
    the composition root; import-safe and idempotent-friendly."""
    app.add_middleware(MetricsMiddleware)

    async def metrics() -> Response:
        return PlainTextResponse(render_prometheus(), media_type=CONTENT_TYPE)

    app.add_api_route("/metrics", metrics, methods=["GET"], name="metrics")


__all__ = [
    "CONTENT_TYPE",
    "Counter",
    "Histogram",
    "HTTP_REQUESTS",
    "HTTP_LATENCY",
    "RUNS_TOTAL",
    "JOBS_TOTAL",
    "inc_run",
    "inc_job",
    "render_prometheus",
    "normalize_path",
    "MetricsMiddleware",
    "add_metrics",
]
