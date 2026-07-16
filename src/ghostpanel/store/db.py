"""Async database engine + session factory. FROZEN foundation.

One async engine per process, built from ``Settings.effective_database_url``
(SQLite for dev/test, Postgres for prod). ``init_db`` creates tables from the
SQLModel metadata (fine for dev/SQLite; Postgres prod should later adopt Alembic
migrations — tracked in docs/deploy.md). ``session_scope`` yields an
``AsyncSession`` with commit/rollback handling.
"""

from __future__ import annotations

import contextlib
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

# Import models so SQLModel.metadata is populated before create_all.
from . import models as _models  # noqa: F401

_engine: Optional[AsyncEngine] = None


def make_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Create an async engine. SQLite needs check_same_thread off for pooling."""
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_async_engine(database_url, echo=echo, future=True,
                               connect_args=connect_args)


def get_engine(database_url: Optional[str] = None) -> AsyncEngine:
    """Return the process-global engine, creating it on first use."""
    global _engine
    if _engine is None:
        if database_url is None:
            from ghostpanel.server.config import get_settings
            database_url = get_settings().effective_database_url
        _engine = make_engine(database_url)
    return _engine


def set_engine(engine: Optional[AsyncEngine]) -> None:
    """Test seam: install (or clear) the process-global engine."""
    global _engine
    _engine = engine


async def init_db(engine: Optional[AsyncEngine] = None) -> None:
    """Create all tables from the SQLModel metadata."""
    eng = engine or get_engine()
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


@contextlib.asynccontextmanager
async def session_scope(
    engine: Optional[AsyncEngine] = None,
) -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession; commit on success, rollback on error."""
    eng = engine or get_engine()
    session = SQLModelAsyncSession(eng, expire_on_commit=False)
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


__all__ = ["make_engine", "get_engine", "set_engine", "init_db", "session_scope"]
