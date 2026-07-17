"""Regression test for the SSRF guard on the hosted enqueue path (finding #1 in
docs/security-audit.md): POST /v2/runs must reject internal/loopback/metadata URLs
before a job is created."""

from __future__ import annotations

import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ghostpanel.jobs.queue import JobQueue
from ghostpanel.server.hosted import register_hosted
from ghostpanel.store import db
from ghostpanel.store.repo import Store


@pytest.fixture()
def client():
    engine = db.make_engine("sqlite+aiosqlite:///" + tempfile.mktemp(suffix=".db"))

    class _S:
        session_secret = "test-secret-abcdefghijklmnop"
        session_ttl_hours = 720
        stripe_secret_key = ""
        stripe_webhook_secret = ""
        stripe_price_team = ""
        has_stripe = False
        is_production = False
        session_cookie_secure = False

    app = FastAPI()

    # Bind the engine + create tables inside startup so aiosqlite connections
    # live on TestClient's event loop (avoids cross-loop errors).
    @app.on_event("startup")
    async def _startup() -> None:  # noqa: ANN202
        db.set_engine(engine)
        await db.init_db(engine)

    register_hosted(app, store=Store(), queue=JobQueue(), storage=object(), settings=_S())
    with TestClient(app) as c:
        yield c
    db.set_engine(None)


def _api_key(client: TestClient) -> str:
    r = client.post("/v2/auth/signup", json={"email": "s@x.co", "password": "pw12345678"})
    token = r.json()["token"]
    pid = r.json()["project"]["id"]
    k = client.post(
        f"/v2/projects/{pid}/keys",
        json={"name": "ci"},
        headers={"Authorization": f"Bearer {token}"},
    )
    return k.json()["plaintext"]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost:8000/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://10.0.0.5/internal",
        "ftp://example.com/x",
    ],
)
def test_enqueue_rejects_unsafe_urls(client, url):
    key = _api_key(client)
    r = client.post(
        "/v2/runs",
        # authorized=True so we exercise the SSRF guard, not the attestation gate.
        json={"url": url, "task": "do it", "authorized": True},
        headers={"X-API-Key": key},
    )
    assert r.status_code == 400, (url, r.status_code, r.text)
    assert "unsafe" in r.json()["detail"].lower()


def test_enqueue_accepts_public_https(client, monkeypatch):
    # Avoid a real DNS lookup: treat the host as resolving to a public IP.
    import ghostpanel.cli.safety as safety

    monkeypatch.setattr(
        safety.socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    key = _api_key(client)
    r = client.post(
        "/v2/runs",
        json={
            "url": "https://app.example.com/checkout",
            "task": "buy",
            "authorized": True,
        },
        headers={"X-API-Key": key},
    )
    assert r.status_code == 202, r.text
