"""End-to-end smoke for the hosted flow, fully offline (P5-A).

Exercises the whole product path without any external API:

  signup -> create project -> create API key   (over the real /v2 HTTP surface
  via ``TestClient(create_app(launch_browser=False))``), then drives the worker's
  ``run_job`` DIRECTLY with a real headless Chromium + a ``FakeHoloClient`` against
  the bundled ``fixtures/hostile_form.html``, and asserts the run lands FINISHED
  with a persisted report + published artifacts.

Determinism / offline: no Holo, Gradium, or Anthropic keys are needed — the
``FakeHoloClient`` returns scripted/center clicks and voice is off. The browser
half is gated: if Chromium isn't installed the test skips *after* the non-browser
HTTP assertions have run, so CI without browsers still passes those.

Event loops: the HTTP setup runs in TestClient's own portal loop and commits to a
temp SQLite *file*; the ``run_job`` half runs under its own ``asyncio.run`` loop
with a fresh engine bound to that loop, reading the same file. This mirrors the
file-based, loop-independent pattern used by ``tests/server_v2/test_api.py``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from ghostpanel.store import db
from ghostpanel.store.models import JobState, RunState

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = _REPO_ROOT / "fixtures" / "hostile_form.html"


# --------------------------------------------------------------------------- #
# response-shape helpers (mirrors tests/server_v2/test_api.py)
# --------------------------------------------------------------------------- #
def _project_id_of(body: dict) -> Optional[str]:
    proj = body.get("project")
    if isinstance(proj, dict) and proj.get("id"):
        return proj["id"]
    projs = body.get("projects")
    if isinstance(projs, list) and projs and isinstance(projs[0], dict):
        return projs[0].get("id")
    return body.get("project_id") or body.get("id")


def _plaintext_key_of(body: dict) -> Optional[str]:
    for k in ("key", "plaintext", "api_key", "secret", "value"):
        v = body.get(k)
        if isinstance(v, str) and v.startswith("sl_live_"):
            return v
    return None


# --------------------------------------------------------------------------- #
# the browser half — driven under its own event loop
# --------------------------------------------------------------------------- #
async def _drive_run_job(*, db_url: str, project_id: str, settings, storage) -> str:
    """Enqueue a job for ``project_id`` and drive ``run_job`` to completion with a
    real headless Chromium + FakeHoloClient. Skips if Chromium isn't installed.

    Runs the DB access on a fresh engine bound to THIS loop (the caller's
    ``asyncio.run`` loop), reading the same SQLite file the HTTP setup wrote.
    Returns the run_id and asserts the run + job + artifacts along the way.
    """
    from playwright.async_api import async_playwright

    from ghostpanel.engine.holo_client import FakeHoloClient
    from ghostpanel.jobs.queue import JobQueue
    from ghostpanel.jobs.worker import run_job
    from ghostpanel.store.repo import Store

    # Fresh engine on this loop; init_db is idempotent (tables already exist).
    db.set_engine(db.make_engine(db_url))
    await db.init_db()

    store = Store()
    queue = JobQueue()

    pw = await async_playwright().start()
    try:
        exe = pw.chromium.executable_path
        if not exe or not Path(exe).exists():
            pytest.skip(
                "Chromium not installed — run `python -m playwright install chromium`"
            )

        target_url = _FIXTURE.resolve().as_uri()
        # impatient-mobile has the tightest budget (max_steps=8), so the fake
        # center-clicking swarm reaches a verdict fast; keeps the test well under 60s.
        job = await queue.enqueue(
            project_id,
            {
                "url": target_url,
                "task": "sign up for an account",
                "persona_ids": ["impatient-mobile"],
                "flow_name": "signup",
            },
        )

        browser = await pw.chromium.launch(headless=True)
        try:
            run_id = await run_job(
                job,
                store=store,
                queue=queue,
                storage=storage,
                settings=settings,
                browser=browser,
                holo_client=FakeHoloClient(),
            )
        finally:
            await browser.close()

        assert run_id, "run_job returned an empty run_id"

        # The run persisted FINISHED with a report.
        row = await store.get_run(run_id)
        assert row is not None, "no RunRow was written"
        assert row.state == RunState.FINISHED, f"run ended {row.state}, error={row.error!r}"
        assert row.report_json is not None, "run finished without a report_json"
        assert row.completion_rate is not None, "completion_rate not promoted"

        # The job was marked DONE.
        done = await queue.get_job(job.id)
        assert done is not None and done.state == JobState.DONE, (
            f"job ended {done.state if done else None}, error={done.error if done else ''!r}"
        )

        # Artifacts exist: the report next to the run dir, and the published copy.
        run_dir = Path(settings.artifact_dir) / run_id
        assert run_dir.is_dir(), f"missing artifact dir {run_dir}"
        assert (run_dir / "report.html").is_file(), "report.html was not written"

        published = storage.root / run_id
        assert published.is_dir() and any(published.rglob("*")), (
            "no artifacts were published to storage"
        )
        return run_id
    finally:
        await pw.stop()
        eng = db.get_engine()
        await eng.dispose()
        db.set_engine(None)


# --------------------------------------------------------------------------- #
# the test
# --------------------------------------------------------------------------- #
def test_hosted_flow_offline(tmp_path, monkeypatch):
    from ghostpanel.server.config import get_settings

    dbfile = tmp_path / "e2e.db"
    db_url = f"sqlite+aiosqlite:///{dbfile}"
    art_dir = tmp_path / "artifacts"
    published_dir = tmp_path / "published"

    # Point the app (and its cached Settings) at the temp DB + a temp artifact dir.
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("GHOSTPANEL_ARTIFACT_DIR", str(art_dir))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    # Ensure no lingering global engine/settings from another test bleeds in.
    get_settings.cache_clear()
    db.set_engine(None)

    try:
        from ghostpanel.app import create_app
        from ghostpanel.server.config import Settings
        from ghostpanel.storage.local import LocalArtifactStorage

        # ---- non-browser: real /v2 HTTP flow (always runs) --------------------
        app = create_app(launch_browser=False)
        with TestClient(app) as c:
            signup = c.post(
                "/v2/auth/signup",
                json={"email": "cohort01@example.com", "password": "hunter2hunter2"},
            )
            assert signup.status_code in (200, 201), signup.text
            assert "sl_session" in c.cookies  # session cookie set on signup

            project = c.post("/v2/projects", json={"name": "E2E Smoke"})
            assert project.status_code in (200, 201), project.text
            project_id = _project_id_of(project.json()) or project.json().get("id")
            assert project_id, f"no project id in {project.json()!r}"

            keys = c.post(f"/v2/projects/{project_id}/keys", json={"name": "ci"})
            assert keys.status_code in (200, 201), keys.text
            plaintext = _plaintext_key_of(keys.json())
            assert plaintext and plaintext.startswith("sl_live_"), "no plaintext API key"

        # ---- browser: drive run_job directly (skips without Chromium) ---------
        settings = Settings(
            database_url=db_url,
            artifact_dir=art_dir,
            storage_backend="local",
            session_secret="e2e-secret",
        )
        storage = LocalArtifactStorage(published_dir)

        asyncio.run(
            _drive_run_job(
                db_url=db_url,
                project_id=project_id,
                settings=settings,
                storage=storage,
            )
        )
    finally:
        get_settings.cache_clear()
        db.set_engine(None)
