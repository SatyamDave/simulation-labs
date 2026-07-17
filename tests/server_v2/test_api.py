"""Hosted API (P2-E) surface tests — TestClient over ``register_hosted``.

Real Store + real JobQueue on a temp SQLite DB. Nothing about the swarm/worker is
exercised: ``POST /v2/runs`` only enqueues a job row, so no browser/Holo mocking is
needed. Job-row persistence is verified by reading the SQLite file directly with the
stdlib ``sqlite3`` driver (loop-independent), sidestepping any cross-event-loop use
of the async engine.

The whole module is xfailed (``strict=False``) until BOTH ``server.hosted`` exists
and ``jobs.queue`` is implemented; it flips to real coverage as those land.
"""

from __future__ import annotations

import inspect
import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

try:
    from ghostpanel.server.hosted import register_hosted
    _HOSTED_IMPORT_ERR: Exception | None = None
except Exception as exc:  # noqa: BLE001 - module may not exist yet (P2-E pending)
    register_hosted = None  # type: ignore[assignment]
    _HOSTED_IMPORT_ERR = exc


def _is_stub(fn) -> bool:
    try:
        return "NotImplementedError" in inspect.getsource(fn)
    except (OSError, TypeError):
        return False


def _api_blocked() -> tuple[bool, str]:
    if register_hosted is None:
        return True, f"server.hosted.register_hosted unavailable ({_HOSTED_IMPORT_ERR!r})"
    from ghostpanel.jobs.queue import JobQueue

    if _is_stub(JobQueue.enqueue):
        return True, "jobs.queue.JobQueue still a stub (P2-D not landed)"
    return False, ""


_BLOCKED, _REASON = _api_blocked()

pytestmark = pytest.mark.xfail(_BLOCKED, reason=_REASON, strict=False)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _build_client(tmp_path) -> tuple[TestClient, str]:
    """Build a TestClient over ``register_hosted``. Raises if hosted is missing —
    which, under the module xfail guard, is reported as xfail (not an error)."""
    from ghostpanel.jobs.queue import JobQueue
    from ghostpanel.server.config import Settings
    from ghostpanel.storage.local import LocalArtifactStorage
    from ghostpanel.store import db
    from ghostpanel.store.repo import Store

    dbfile = tmp_path / "api.db"
    url = f"sqlite+aiosqlite:///{dbfile}"
    settings = Settings(
        database_url=url,
        session_secret="api-test-secret",
        artifact_dir=tmp_path / "artifacts",
        storage_backend="local",
    )

    app = FastAPI()

    @app.on_event("startup")
    async def _startup():
        engine = db.make_engine(url)
        db.set_engine(engine)
        await db.init_db(engine)

    @app.on_event("shutdown")
    async def _shutdown():
        engine = db.get_engine()
        await engine.dispose()
        db.set_engine(None)

    register_hosted(
        app,
        store=Store(),
        queue=JobQueue(),
        storage=LocalArtifactStorage(settings.artifact_dir),
        settings=settings,
    )
    return TestClient(app), str(dbfile)


def _token_of(body: dict):
    for k in ("token", "session_token", "access_token", "jwt"):
        v = body.get(k)
        if isinstance(v, str):
            return v
    sess = body.get("session")
    if isinstance(sess, str):
        return sess
    if isinstance(sess, dict):
        for k in ("token", "access_token"):
            if isinstance(sess.get(k), str):
                return sess[k]
    return None


def _project_id_of(body: dict):
    proj = body.get("project")
    if isinstance(proj, dict) and proj.get("id"):
        return proj["id"]
    projs = body.get("projects")
    if isinstance(projs, list) and projs and isinstance(projs[0], dict):
        return projs[0].get("id")
    return body.get("project_id")


def _plaintext_key_of(body: dict):
    for k in ("key", "plaintext", "api_key", "secret", "value"):
        v = body.get(k)
        if isinstance(v, str) and v.startswith("sl_live_"):
            return v
    return None


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #
def test_signup_sets_cookie_and_me_requires_auth(tmp_path):
    client, _dbfile = _build_client(tmp_path)
    with client as c:
        # Unauthenticated /me -> 401.
        assert c.get("/v2/auth/me").status_code == 401

        resp = c.post(
            "/v2/auth/signup",
            json={"email": "founder@example.com", "password": "hunter2hunter2"},
        )
        assert resp.status_code in (200, 201)
        body = resp.json()
        assert _token_of(body) is not None
        assert "sl_session" in c.cookies  # session cookie set on signup

        # Now the session cookie authenticates /me.
        me = c.get("/v2/auth/me")
        assert me.status_code == 200


def test_create_project_and_api_key_returns_plaintext_once(tmp_path):
    client, _dbfile = _build_client(tmp_path)
    with client as c:
        c.post(
            "/v2/auth/signup",
            json={"email": "founder@example.com", "password": "hunter2hunter2"},
        )
        proj = c.post("/v2/projects", json={"name": "Second Project"})
        assert proj.status_code in (200, 201)
        project_id = _project_id_of({"project": proj.json()}) or proj.json().get("id")
        assert project_id

        keys = c.post(f"/v2/projects/{project_id}/keys", json={"name": "ci"})
        assert keys.status_code in (200, 201)
        plaintext = _plaintext_key_of(keys.json())
        assert plaintext is not None and plaintext.startswith("sl_live_")


def test_post_run_enqueues_job(tmp_path):
    client, dbfile = _build_client(tmp_path)
    with client as c:
        signup = c.post(
            "/v2/auth/signup",
            json={"email": "founder@example.com", "password": "hunter2hunter2"},
        )
        project_id = _project_id_of(signup.json())
        assert project_id

        keys = c.post(f"/v2/projects/{project_id}/keys", json={"name": "ci"})
        plaintext = _plaintext_key_of(keys.json())
        assert plaintext is not None

        run = c.post(
            "/v2/runs",
            headers={"X-API-Key": plaintext},
            json={
                "url": "https://example.com/signup",
                "task": "sign up for an account",
                "flow_name": "signup",
                "authorized": True,
            },
        )
        assert run.status_code in (200, 201, 202)  # 202 Accepted (enqueued)
        job_id = run.json().get("job_id")
        assert job_id

    # A job row was durably written for this project (read the file directly).
    conn = sqlite3.connect(dbfile)
    try:
        rows = conn.execute("SELECT id, project_id FROM jobs").fetchall()
    finally:
        conn.close()
    assert any(jid == job_id for (jid, _pid) in rows)
    assert all(pid == project_id for (_jid, pid) in rows)


def test_run_rejected_without_authorization(tmp_path):
    """Authorization gate: POST /v2/runs is rejected (403) when the caller does
    not attest ownership/permission for the target site — enforced server-side,
    before any job is enqueued."""
    client, dbfile = _build_client(tmp_path)
    with client as c:
        signup = c.post(
            "/v2/auth/signup",
            json={"email": "founder@example.com", "password": "hunter2hunter2"},
        )
        project_id = _project_id_of(signup.json())
        keys = c.post(f"/v2/projects/{project_id}/keys", json={"name": "ci"})
        plaintext = _plaintext_key_of(keys.json())

        # Missing attestation -> defaults to false -> 403.
        r = c.post(
            "/v2/runs",
            headers={"X-API-Key": plaintext},
            json={"url": "https://example.com/signup", "task": "sign up"},
        )
        assert r.status_code == 403, r.text
        assert "authoriz" in r.json()["detail"].lower()

        # Explicit false -> still 403.
        r = c.post(
            "/v2/runs",
            headers={"X-API-Key": plaintext},
            json={
                "url": "https://example.com/signup",
                "task": "sign up",
                "authorized": False,
            },
        )
        assert r.status_code == 403, r.text

    # No job row was written for the rejected requests.
    conn = sqlite3.connect(dbfile)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
    finally:
        conn.close()
    assert count == 0


def test_run_accepted_with_authorization_persists_attestation(tmp_path):
    """With the attestation the run is enqueued (202) and the audit record
    (who / when / which domain) is persisted in the durable job spec."""
    client, dbfile = _build_client(tmp_path)
    with client as c:
        signup = c.post(
            "/v2/auth/signup",
            json={"email": "founder@example.com", "password": "hunter2hunter2"},
        )
        project_id = _project_id_of(signup.json())
        keys = c.post(f"/v2/projects/{project_id}/keys", json={"name": "ci"})
        plaintext = _plaintext_key_of(keys.json())

        r = c.post(
            "/v2/runs",
            headers={"X-API-Key": plaintext},
            json={
                "url": "https://example.com/checkout",
                "task": "buy",
                "authorized": True,
            },
        )
        assert r.status_code == 202, r.text

    # The job spec carries the attestation audit trail.
    conn = sqlite3.connect(dbfile)
    try:
        rows = conn.execute("SELECT spec FROM jobs").fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    spec = json.loads(rows[0][0])
    att = spec["attestation"]
    assert att["authorized"] is True
    assert att["authorized_by"] == project_id
    assert att["authorized_domain"] == "example.com"
    assert att["authorized_at"]  # ISO timestamp present


def test_runs_history_requires_auth_and_is_scoped(tmp_path):
    client, _dbfile = _build_client(tmp_path)
    with client as c:
        signup = c.post(
            "/v2/auth/signup",
            json={"email": "founder@example.com", "password": "hunter2hunter2"},
        )
        project_id = _project_id_of(signup.json())
        keys = c.post(f"/v2/projects/{project_id}/keys", json={"name": "ci"})
        plaintext = _plaintext_key_of(keys.json())
        assert plaintext is not None

        # Unauthenticated history -> 401.
        c.cookies.clear()
        assert c.get("/v2/runs").status_code == 401

        # API-key-scoped history -> 200, a JSON list.
        listing = c.get("/v2/runs", headers={"X-API-Key": plaintext})
        assert listing.status_code == 200
        payload = listing.json()
        runs = payload if isinstance(payload, list) else payload.get("runs")
        assert isinstance(runs, list)


def test_cross_project_access_is_forbidden(tmp_path):
    client, _dbfile = _build_client(tmp_path)
    with client as c:
        r1 = c.post(
            "/v2/auth/signup",
            json={"email": "user1@example.com", "password": "hunter2hunter2"},
        )
        token1 = _token_of(r1.json())
        assert token1 is not None

        c.cookies.clear()
        r2 = c.post(
            "/v2/auth/signup",
            json={"email": "user2@example.com", "password": "hunter2hunter2"},
        )
        other_project = _project_id_of(r2.json())
        assert other_project

        # User 1 (bearer JWT, cookies cleared) may not read user 2's project.
        c.cookies.clear()
        resp = c.get(
            f"/v2/projects/{other_project}",
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert resp.status_code == 403
