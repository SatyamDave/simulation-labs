"""Auth (P2-C) tests — passwords, session tokens, api keys, and FastAPI deps.

All of ``auth/*`` is implemented, so these are expected to PASS. The ``deps``
test spins up a tiny FastAPI app (one route per dependency) with a REAL Store on a
temp SQLite DB and exercises it through the TestClient. The engine is created
inside the app's startup event so aiosqlite connections stay on the TestClient's
event loop, and torn down on shutdown.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from ghostpanel.auth import deps as authdeps
from ghostpanel.auth.apikeys import (
    KEY_PREFIX,
    generate_api_key,
    prefix_of,
    verify_api_key,
)
from ghostpanel.auth.passwords import hash_password, verify_password
from ghostpanel.auth.tokens import (
    InvalidToken,
    decode_session_token,
    issue_session_token,
)


# --------------------------------------------------------------------------- #
# passwords
# --------------------------------------------------------------------------- #
def test_password_roundtrip_and_wrong():
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert verify_password("correct horse battery staple", h) is True
    assert verify_password("wrong password", h) is False


def test_password_verify_never_raises_on_malformed():
    # Malformed / empty hash must return False, not raise.
    assert verify_password("anything", "not-a-bcrypt-hash") is False
    assert verify_password("anything", "") is False


def test_password_long_passphrase_does_not_raise():
    long = "x" * 500  # exceeds bcrypt's 72-byte limit; must be truncated, not error
    h = hash_password(long)
    assert verify_password(long, h) is True


# --------------------------------------------------------------------------- #
# session tokens
# --------------------------------------------------------------------------- #
def test_token_issue_then_decode():
    secret = "unit-test-secret"
    token = issue_session_token("user-42", secret)
    assert decode_session_token(token, secret) == "user-42"


def test_token_empty_secret_rejected():
    with pytest.raises(ValueError):
        issue_session_token("u", "")


def test_token_tampered_or_wrong_secret_raises():
    secret = "unit-test-secret"
    token = issue_session_token("user-42", secret)
    with pytest.raises(InvalidToken):
        decode_session_token(token + "tamper", secret)
    with pytest.raises(InvalidToken):
        decode_session_token(token, "a-different-secret")


def test_token_expired_raises():
    secret = "unit-test-secret"
    expired = issue_session_token("user-42", secret, ttl_hours=-1)
    with pytest.raises(InvalidToken):
        decode_session_token(expired, secret)


# --------------------------------------------------------------------------- #
# api keys
# --------------------------------------------------------------------------- #
def test_apikey_generate_verify_and_prefix():
    prefix, plaintext, key_hash = generate_api_key()
    assert prefix.startswith(KEY_PREFIX)
    assert plaintext.startswith(prefix + "_")
    assert verify_api_key(plaintext, key_hash) is True
    assert verify_api_key("sl_live_deadbeef_bogussecret", key_hash) is False
    assert prefix_of(plaintext) == prefix
    assert prefix_of("not-a-key") == ""


# --------------------------------------------------------------------------- #
# FastAPI dependencies (integration through a tiny app)
# --------------------------------------------------------------------------- #
@pytest.fixture
def deps_ctx(tmp_path):
    from ghostpanel.server.config import Settings
    from ghostpanel.store import db
    from ghostpanel.store.repo import Store

    url = f"sqlite+aiosqlite:///{tmp_path / 'deps.db'}"
    settings = Settings(database_url=url, session_secret="deps-secret")

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
        u1 = await store.create_user("owner@example.com", hash_password("pw"))
        p1 = await store.create_project(owner=u1, name="Owner Project")
        _row, key1 = await store.create_api_key(p1.id)
        u2 = await store.create_user("stranger@example.com", hash_password("pw"))
        p2 = await store.create_project(owner=u2, name="Stranger Project")
        seed.update(
            u1_id=u1.id,
            p1_id=p1.id,
            key1=key1,
            p2_id=p2.id,
            token1=issue_session_token(u1.id, settings.session_secret),
        )

    @app.on_event("shutdown")
    async def _shutdown():
        engine = db.get_engine()
        await engine.dispose()
        db.set_engine(None)

    @app.get("/me")
    async def me(user=Depends(authdeps.current_user)):
        return {"id": user.id}

    @app.get("/project")
    async def project(project=Depends(authdeps.current_project)):
        return {"id": project.id}

    @app.get("/access/{project_id}")
    async def access(project_id: str, project=Depends(authdeps.require_project_access)):
        return {"id": project.id}

    with TestClient(app) as client:
        yield client, seed


def test_current_user_dep_valid_and_missing(deps_ctx):
    client, seed = deps_ctx
    # Missing session -> 401.
    assert client.get("/me").status_code == 401
    # Valid session cookie -> 200 + the right user.
    client.cookies.set(authdeps.SESSION_COOKIE, seed["token1"])
    resp = client.get("/me")
    assert resp.status_code == 200 and resp.json()["id"] == seed["u1_id"]


def test_current_project_dep_apikey(deps_ctx):
    client, seed = deps_ctx
    assert client.get("/project").status_code == 401
    resp = client.get("/project", headers={"X-API-Key": seed["key1"]})
    assert resp.status_code == 200 and resp.json()["id"] == seed["p1_id"]


def test_require_project_access_own_vs_wrong_project(deps_ctx):
    client, seed = deps_ctx
    client.cookies.set(authdeps.SESSION_COOKIE, seed["token1"])
    # Owner can reach their own project.
    assert client.get(f"/access/{seed['p1_id']}").status_code == 200
    # ...but not a project they are not a member of -> 403.
    assert client.get(f"/access/{seed['p2_id']}").status_code == 403
