"""Observability (P5-B): request-scoped logging + a readiness probe.

Stdlib-``logging`` only, no new deps. ``add_observability(app)`` is the single
entry point the composition root (``app.py``) calls: it installs
``RequestContextMiddleware`` (which stamps every request/response with an
``X-Request-ID`` and emits one structured JSON access log line) and registers a
cheap ``GET /readyz`` probe that pings the database.

Everything here is import-safe: no DB connection, no logging side effects happen
at import time — only when ``add_observability`` / ``configure_logging`` run.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_REQUEST_ID_HEADER = "X-Request-ID"
_ACCESS_LOGGER = "ghostpanel.access"

# LogRecord attributes present on every record; anything else on the record is a
# caller-supplied ``extra`` we want to surface in the JSON line.
_RESERVED_LOG_ATTRS = frozenset(
    logging.makeLogRecord({}).__dict__.keys()
) | {"message", "asctime"}


class JsonLogFormatter(logging.Formatter):
    """Render each record as a single ``json.dumps`` line.

    Emits the standard fields (timestamp, level, logger name, message) plus any
    ``extra=`` keys bound onto the record (e.g. request_id/method/path/status/
    duration_ms from the access logger). Exception info is included if present.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_ATTRS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        try:
            return json.dumps(payload, default=str)
        except (TypeError, ValueError):
            # Never let a non-serializable extra crash logging.
            return json.dumps({"level": record.levelname, "logger": record.name,
                               "message": record.getMessage()})


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger's stream handler.

    Idempotent: if a handler we own already exists it is reused (formatter +
    level refreshed) rather than stacked, so repeated calls don't multiply log
    lines.
    """
    root = logging.getLogger()
    root.setLevel(level)

    formatter = JsonLogFormatter()
    owned = [h for h in root.handlers if getattr(h, "_ghostpanel_json", False)]
    if owned:
        for handler in owned:
            handler.setFormatter(formatter)
            handler.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.setLevel(level)
    handler._ghostpanel_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign an ``X-Request-ID`` to every request, time it, and emit one
    structured access log line on completion. Logging failures never break the
    response."""

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001, ANN201
        incoming = request.headers.get(_REQUEST_ID_HEADER)
        request_id = incoming or uuid.uuid4().hex
        request.state.request_id = request_id

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 3)

        response.headers[_REQUEST_ID_HEADER] = request_id

        try:
            logging.getLogger(_ACCESS_LOGGER).info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        except Exception:  # noqa: BLE001 - observability must never break serving
            pass

        return response


async def _db_ok() -> bool:
    """Cheap ``SELECT 1`` against the process engine. False on any error."""
    try:
        from sqlalchemy import text

        from ghostpanel.store.db import get_engine

        async with get_engine().begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - degrade, never raise
        return False


def add_observability(app) -> None:  # noqa: ANN001
    """Wire observability into ``app``: the request-context middleware and a
    ``GET /readyz`` readiness probe. Called by the composition root."""
    app.add_middleware(RequestContextMiddleware)

    async def readyz() -> dict[str, Any]:
        return {"status": "ok", "db": await _db_ok()}

    app.add_api_route("/readyz", readyz, methods=["GET"], name="readyz")


__all__ = [
    "JsonLogFormatter",
    "RequestContextMiddleware",
    "configure_logging",
    "add_observability",
]
