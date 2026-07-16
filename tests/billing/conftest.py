"""Shared fixtures + guards for the billing/tenancy test suite (P4-D).

Every test that touches the DB gets a fresh, isolated SQLite file wired into the
process-global engine that ``ghostpanel.store.db.session_scope`` resolves — the
same pattern the Store suite uses (``tests/store/conftest.py``). The engine is
created inside the test's own event loop (pytest-asyncio ``auto`` mode) so the
aiosqlite connections stay bound to a single loop.

``is_stub`` lets the individual test modules xfail themselves while a sibling
module they depend on (P4-A usage / stripe_client, P4-B routers) is still a stub,
so the suite is green today and flips to real coverage as those land.
"""

from __future__ import annotations

import inspect

import pytest

from ghostpanel.store import db


def is_stub(fn) -> bool:
    """True if ``fn``'s source still raises NotImplementedError (unimplemented)."""
    try:
        return "NotImplementedError" in inspect.getsource(fn)
    except (OSError, TypeError):
        return False


@pytest.fixture
async def db_engine(tmp_path):
    """A fresh temp-SQLite engine installed as the process-global engine."""
    engine = db.make_engine(f"sqlite+aiosqlite:///{tmp_path / 'billing.db'}")
    db.set_engine(engine)
    await db.init_db(engine)
    try:
        yield engine
    finally:
        db.set_engine(None)
        await engine.dispose()
