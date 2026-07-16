"""Shared fixtures for the JobQueue test suite (P2-G).

Fresh SQLite file per test, wired into the process-global engine. Also seeds a
project so enqueued jobs have a real ``project_id`` (mirrors production even
though SQLite FK enforcement is off by default).
"""

from __future__ import annotations

import pytest

from ghostpanel.store import db


@pytest.fixture
async def job_ctx(tmp_path):
    from ghostpanel.jobs.queue import JobQueue
    from ghostpanel.store.repo import Store

    engine = db.make_engine(f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}")
    db.set_engine(engine)
    await db.init_db(engine)

    store = Store()
    user = await store.create_user("jobs@example.com", "hash")
    project = await store.create_project(owner=user, name="Jobs Project")

    try:
        yield store, JobQueue(), project.id
    finally:
        db.set_engine(None)
        await engine.dispose()
