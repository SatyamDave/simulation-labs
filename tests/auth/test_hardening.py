"""SEC-B auth-hardening tests — rate limiting + stateless recovery flows.

The recovery tests spin up a tiny FastAPI app that mounts BOTH the session-auth
router (``routers.auth``, for login) and the account router (``routers.account``)
against a REAL ``Store`` on a temp SQLite DB — mirroring the engine-on-startup
pattern from ``tests/auth/test_auth.py`` so aiosqlite stays on the TestClient's
event loop.
"""

from __future__ import annotations

import time

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from ghostpanel.auth.passwords import hash_password
from ghostpanel.auth.ratelimit import RateLimiter, client_ip, limit_by_ip


# --------------------------------------------------------------------------- #
# RateLimiter (pure, no app)
# --------------------------------------------------------------------------- #
def test_ratelimiter_blocks_after_n_and_recovers():
    rl = RateLimiter(max=3, per_seconds=0.3)
    assert [rl.allow("ip-a") for _ in range(3)] == [True, True, True]
    # 4th within the window is blocked...
    assert rl.allow("ip-a") is False
    assert rl.allow("ip-a") is False
    # ...but a different key has its own budget.
    assert rl.allow("ip-b") is True
    # After the window elapses, the key recovers.
    time.sleep(0.35)
    assert rl.allow("ip-a") is True


def test_ratelimiter_validates_args():
    with pytest.raises(ValueError):
        RateLimiter(max=0, per_seconds=1)
    with pytest.raises(ValueError):
        RateLimiter(max=1, per_seconds=0)


def test_limit_by_ip_dependency_429_and_xff_keying():
    app = FastAPI()

    @app.get("/ping", dependencies=[Depends(limit_by_ip("ping", 2, 60))])
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    # Same client IP → 3rd is throttled, with a Retry-After header.
    blocked = client.get("/ping")
    assert blocked.status_code == 429
    assert "retry-after" in {k.lower() for k in blocked.headers}
    # A distinct X-Forwarded-For first hop is treated as a different client.
    assert client.get("/ping", headers={"X-Forwarded-For": "9.9.9.9, 10.0.0.1"}).status_code == 200


def test_client_ip_prefers_xff_first_hop():
    class _FakeClient:
        host = "127.0.0.1"

    class _FakeReq:
        def __init__(self, headers):
            self.headers = headers
            self.client = _FakeClient()

    assert client_ip(_FakeReq({"x-forwarded-for": "1.2.3.4, 5.6.7.8"})) == "1.2.3.4"
    assert client_ip(_FakeReq({})) == "127.0.0.1"


# --------------------------------------------------------------------------- #
# Recovery flows (integration through a real Store + TestClient)
# --------------------------------------------------------------------------- #
@pytest.fixture
def app_ctx(tmp_path):
    from ghostpanel.server.config import Settings
    from ghostpanel.server.routers import account as account_router
    from ghostpanel.server.routers import auth as auth_router
    from ghostpanel.store import db
    from ghostpanel.store.repo import Store

    url = f"sqlite+aiosqlite:///{tmp_path / 'hardening.db'}"
    settings = Settings(database_url=url, session_secret="hardening-secret")

    app = FastAPI()
    app.state.store = Store()
    app.state.settings = settings
    seed: dict[str, str] = {}

    @app.on_event("startup")
    async def _startup():
        engine = db.make_engine(url)
        db.set_engine(engine)
        await db.init_db(engine)
        store: Store = app.state.store
        u = await store.create_user("known@example.com", hash_password("originalpw1"))
        await store.create_project(owner=u, name="Default")
        seed["uid"] = u.id

    @app.on_event("shutdown")
    async def _shutdown():
        engine = db.get_engine()
        await engine.dispose()
        db.set_engine(None)

    app.include_router(auth_router.router)
    app.include_router(account_router.router)

    with TestClient(app) as client:
        yield client, seed, settings


def test_password_reset_round_trip(app_ctx):
    client, _seed, _settings = app_ctx
    # 1) request a reset token (dev returns it inline)
    r = client.post(
        "/v2/auth/request-password-reset", json={"email": "known@example.com"}
    )
    assert r.status_code == 200
    token = r.json()["reset_token"]

    # 2) redeem it for a new password
    r2 = client.post(
        "/v2/auth/reset-password",
        json={"token": token, "new_password": "brandnewpw9"},
    )
    assert r2.status_code == 200

    # 3) the old password is dead, the new one logs in
    old = client.post(
        "/v2/auth/login",
        json={"email": "known@example.com", "password": "originalpw1"},
    )
    assert old.status_code == 401
    new = client.post(
        "/v2/auth/login",
        json={"email": "known@example.com", "password": "brandnewpw9"},
    )
    assert new.status_code == 200


def test_reset_rejects_expired_token(app_ctx):
    from ghostpanel.server.routers import account

    client, seed, settings = app_ctx
    expired = account._issue_purpose_token(
        seed["uid"], settings.session_secret, account._TYP_PWRESET, ttl_minutes=-1
    )
    r = client.post(
        "/v2/auth/reset-password",
        json={"token": expired, "new_password": "whatevers8"},
    )
    assert r.status_code == 400


def test_reset_rejects_wrong_purpose_token(app_ctx):
    from ghostpanel.server.routers import account

    client, seed, settings = app_ctx
    # A valid *verify* token must not be usable to reset a password.
    verify_tok = account._issue_purpose_token(
        seed["uid"], settings.session_secret, account._TYP_VERIFY, ttl_minutes=60
    )
    r = client.post(
        "/v2/auth/reset-password",
        json={"token": verify_tok, "new_password": "whatevers8"},
    )
    assert r.status_code == 400


def test_reset_rejects_short_password(app_ctx):
    from ghostpanel.server.routers import account

    client, seed, settings = app_ctx
    token = account._issue_purpose_token(
        seed["uid"], settings.session_secret, account._TYP_PWRESET, ttl_minutes=30
    )
    r = client.post(
        "/v2/auth/reset-password", json={"token": token, "new_password": "short7x"}
    )
    assert r.status_code == 422  # pydantic min_length=8 rejection


def test_no_email_enumeration(app_ctx):
    client, _seed, _settings = app_ctx
    known = client.post(
        "/v2/auth/request-password-reset", json={"email": "known@example.com"}
    )
    unknown = client.post(
        "/v2/auth/request-password-reset", json={"email": "nobody@example.com"}
    )
    # Identical status, identical shape, identical human message.
    assert known.status_code == unknown.status_code == 200
    assert set(known.json().keys()) == set(unknown.json().keys())
    assert "reset_token" in known.json() and "reset_token" in unknown.json()
    assert known.json()["message"] == unknown.json()["message"]


def test_unknown_email_token_cannot_reset(app_ctx):
    """The token handed out for an unknown email is well-formed but unredeemable."""
    client, _seed, _settings = app_ctx
    r = client.post(
        "/v2/auth/request-password-reset", json={"email": "nobody@example.com"}
    )
    token = r.json()["reset_token"]
    r2 = client.post(
        "/v2/auth/reset-password",
        json={"token": token, "new_password": "brandnewpw9"},
    )
    assert r2.status_code == 400


def test_verify_email_round_trip(app_ctx):
    client, seed, _settings = app_ctx
    r = client.post("/v2/auth/request-verify", json={"email": "known@example.com"})
    assert r.status_code == 200
    token = r.json()["verify_token"]
    r2 = client.post("/v2/auth/verify-email", json={"token": token})
    assert r2.status_code == 200
    body = r2.json()
    assert body["verified"] is True and body["user_id"] == seed["uid"]


def test_verify_rejects_wrong_purpose_token(app_ctx):
    from ghostpanel.server.routers import account

    client, seed, settings = app_ctx
    # A password-reset token must not verify an email.
    pwreset = account._issue_purpose_token(
        seed["uid"], settings.session_secret, account._TYP_PWRESET, ttl_minutes=30
    )
    r = client.post("/v2/auth/verify-email", json={"token": pwreset})
    assert r.status_code == 400
