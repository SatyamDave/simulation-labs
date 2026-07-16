"""P5-B observability tests — TestClient over a tiny app with add_observability.

Covers: X-Request-ID is stamped on responses and an inbound one is echoed;
``GET /readyz`` returns 200 with ``{status:"ok", db:true}`` against a live temp
SQLite engine; and one structured access log line is emitted per request.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ghostpanel.server.middleware import (
    JsonLogFormatter,
    add_observability,
    configure_logging,
)
from ghostpanel.store import db


@pytest.fixture()
def client(tmp_path):
    """A minimal app with observability wired in, backed by a live temp SQLite
    engine so ``/readyz`` can run a real ``SELECT 1``."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'readyz.db'}"
    engine = db.make_engine(url)
    db.set_engine(engine)

    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    add_observability(app)

    with TestClient(app) as c:
        yield c

    db.set_engine(None)


def test_request_id_is_generated(client):
    resp = client.get("/ping")
    assert resp.status_code == 200
    rid = resp.headers.get("X-Request-ID")
    assert rid and len(rid) >= 8


def test_inbound_request_id_is_echoed(client):
    resp = client.get("/ping", headers={"X-Request-ID": "abc123fixed"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == "abc123fixed"


def test_readyz_ok_on_live_db(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "db": True}


def test_readyz_degrades_without_engine(client):
    # Point the engine at an unreachable/broken URL so SELECT 1 fails; the probe
    # must still answer 200 with db=false rather than raising.
    db.set_engine(db.make_engine("sqlite+aiosqlite:////nonexistent/dir/x.db"))
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": False}


def test_access_log_line_emitted(client, caplog):
    with caplog.at_level(logging.INFO, logger="ghostpanel.access"):
        client.get("/ping")

    records = [r for r in caplog.records if r.name == "ghostpanel.access"]
    assert records, "expected an access log record"
    rec = records[-1]
    assert rec.method == "GET"
    assert rec.path == "/ping"
    assert rec.status == 200
    assert isinstance(rec.duration_ms, (int, float))
    assert rec.request_id


def test_json_formatter_includes_extras():
    configure_logging("INFO")  # idempotent; safe to call in a test
    fmt = JsonLogFormatter()
    record = logging.getLogger("ghostpanel.access").makeRecord(
        "ghostpanel.access", logging.INFO, __file__, 1, "request", None, None,
    )
    record.request_id = "rid-1"
    record.method = "GET"
    record.path = "/ping"
    record.status = 200
    record.duration_ms = 1.5

    payload = json.loads(fmt.format(record))
    assert payload["message"] == "request"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "ghostpanel.access"
    assert payload["request_id"] == "rid-1"
    assert payload["status"] == 200
    assert payload["duration_ms"] == 1.5


def test_configure_logging_is_idempotent():
    root = logging.getLogger()
    configure_logging("INFO")
    owned_before = [h for h in root.handlers if getattr(h, "_ghostpanel_json", False)]
    configure_logging("INFO")
    owned_after = [h for h in root.handlers if getattr(h, "_ghostpanel_json", False)]
    assert len(owned_before) == 1
    assert len(owned_after) == 1
