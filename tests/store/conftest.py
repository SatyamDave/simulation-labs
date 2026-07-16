"""Shared fixtures for the Store test suite (P2-G).

Each test gets a fresh, isolated SQLite file wired into the process-global engine
that ``store.db.session_scope`` resolves. The engine is created inside the test's
own event loop (pytest-asyncio ``auto`` mode) so aiosqlite connections stay bound
to a single loop.
"""

from __future__ import annotations

import pytest

from ghostpanel.store import db


@pytest.fixture
async def db_engine(tmp_path):
    engine = db.make_engine(f"sqlite+aiosqlite:///{tmp_path / 'store.db'}")
    db.set_engine(engine)
    await db.init_db(engine)
    try:
        yield engine
    finally:
        db.set_engine(None)
        await engine.dispose()
