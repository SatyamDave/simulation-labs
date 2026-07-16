"""Authed-artifact route tests (SEC-A) — closes the artifact IDOR (finding #2).

Real ``Store`` + ``LocalArtifactStorage`` on a temp SQLite DB, driven through
``register_hosted`` with the artifacts router mounted. Two tenants are created via
the real signup flow; a run + a seeded artifact belong to tenant A. We assert:

  * a member of A streams the artifact (200 + exact bytes);
  * a valid signed ``?token=`` works without any session;
  * an expired/garbage token with no session → 404;
  * tenant B (member of a different project) → 404 (existence hidden);
  * a path-traversal attempt (``../../secret``) → 404.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

try:
    from ghostpanel.server.hosted import register_hosted
    from ghostpanel.server.routers.artifacts import (
        router as artifacts_router,
        signed_artifact_path,
    )
    _IMPORT_ERR: Exception | None = None
except Exception as exc:  # noqa: BLE001 - modules may not exist yet
    register_hosted = None  # type: ignore[assignment]
    _IMPORT_ERR = exc

pytestmark = pytest.mark.skipif(
    register_hosted is None, reason=f"hosted/artifacts unavailable ({_IMPORT_ERR!r})"
)

SECRET = "artifact-test-secret"
ARTIFACT_REL = "report.html"
ARTIFACT_BYTES = b"<html><body>tenant A secret report</body></html>"
RUN_ID = "run_aaaaaaaaaaaa"


def _build(tmp_path):
    """A TestClient over register_hosted + the artifacts router, plus the shared
    Settings/URL so the test can seed rows and files against the same backends."""
    from ghostpanel.jobs.queue import JobQueue
    from ghostpanel.server.config import Settings
    from ghostpanel.storage.local import LocalArtifactStorage
    from ghostpanel.store import db
    from ghostpanel.store.repo import Store

    dbfile = tmp_path / "artifacts.db"
    url = f"sqlite+aiosqlite:///{dbfile}"
    artifact_dir = tmp_path / "artifacts"
    settings = Settings(
        database_url=url,
        session_secret=SECRET,
        artifact_dir=artifact_dir,
        storage_backend="local",
    )
    storage = LocalArtifactStorage(artifact_dir)

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
        app, store=Store(), queue=JobQueue(), storage=storage, settings=settings
    )
    app.include_router(artifacts_router)
    return TestClient(app), url, artifact_dir, storage


def _signup(c, email):
    body = c.post(
        "/v2/auth/signup", json={"email": email, "password": "hunter2hunter2"}
    ).json()
    return body["token"], body["project"]["id"]


def _seed_run(url: str, project_id: str) -> None:
    """Insert a finished RunRow for ``project_id`` via a throwaway engine on the
    same sqlite file (ORM insert keeps the enum/JSON encoding identical to prod)."""
    from ghostpanel.store import db
    from ghostpanel.store.models import RunRow, RunState

    async def _go():
        eng = db.make_engine(url)
        try:
            async with db.session_scope(eng) as s:
                s.add(
                    RunRow(
                        id=RUN_ID,
                        project_id=project_id,
                        state=RunState.FINISHED,
                        target_url="https://example.com/signup",
                        task="sign up",
                        flow_name="signup",
                        persona_ids=[],
                    )
                )
        finally:
            await eng.dispose()

    asyncio.run(_go())


def test_artifact_authz_and_traversal(tmp_path):
    client, url, artifact_dir, storage = _build(tmp_path)

    with client as c:
        # Two tenants via the real signup flow (each gets its own project).
        token_a, project_a = _signup(c, "a@example.com")
        c.cookies.clear()
        token_b, _project_b = _signup(c, "b@example.com")
        c.cookies.clear()

        # A run owned by tenant A + its artifact on disk under the run dir.
        _seed_run(url, project_a)
        (artifact_dir / RUN_ID).mkdir(parents=True, exist_ok=True)
        (artifact_dir / RUN_ID / ARTIFACT_REL).write_bytes(ARTIFACT_BYTES)
        # A sensitive file OUTSIDE the run dir the traversal must never reach.
        (artifact_dir / "secret").write_bytes(b"OTHER TENANT SECRET")

        route = f"/v2/runs/{RUN_ID}/artifacts/{ARTIFACT_REL}"

        # 1) Member of A streams the artifact.
        r = c.get(route, headers={"Authorization": f"Bearer {token_a}"})
        assert r.status_code == 200, r.text
        assert r.content == ARTIFACT_BYTES
        assert r.headers["content-type"].startswith("text/html")

        # 2) Signed token works with no session at all.
        c.cookies.clear()
        signed = signed_artifact_path(RUN_ID, ARTIFACT_REL, SECRET)
        r = c.get(signed)
        assert r.status_code == 200, r.text
        assert r.content == ARTIFACT_BYTES

        # 3) Expired / garbage token with no session → 404.
        assert c.get(f"{route}?token=deadbeef.notasig").status_code == 404
        expired = f"1.{'x' * 43}"  # exp far in the past → verify_artifact False
        assert c.get(f"{route}?token={expired}").status_code == 404
        # No auth of any kind at all.
        assert c.get(route).status_code == 404

        # 4) Tenant B (member of a different project) → 404, not 403.
        r = c.get(route, headers={"Authorization": f"Bearer {token_b}"})
        assert r.status_code == 404, r.text

        # 5) Path traversal at the route → 404 (auth is valid; storage rejects it).
        for evil in ("..%2f..%2fsecret", "..%2fsecret", "%2e%2e%2f%2e%2e%2fsecret"):
            r = c.get(
                f"/v2/runs/{RUN_ID}/artifacts/{evil}",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert r.status_code == 404, f"{evil!r} -> {r.status_code}"

    # Storage-level traversal defense is deterministic (no route normalization).
    async def _reads():
        assert await storage.read(RUN_ID, ARTIFACT_REL) == ARTIFACT_BYTES
        for evil in ("../secret", "../../secret", "/etc/hostname", "..\\..\\secret"):
            assert await storage.read(RUN_ID, evil) is None, evil
        # Missing file inside the run dir → None (not an error).
        assert await storage.read(RUN_ID, "nope.txt") is None

    asyncio.run(_reads())


def test_presigned_url_is_none_for_local(tmp_path):
    _client, _url, _artifact_dir, storage = _build(tmp_path)
    assert storage.presigned_url(RUN_ID, ARTIFACT_REL) is None
