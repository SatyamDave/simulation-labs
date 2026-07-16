"""Alembic environment for Ghostpanel.

Design decision — **synchronous migrations against a sync driver**.

The app runs on an async SQLAlchemy engine (``sqlite+aiosqlite`` in dev,
``postgresql+asyncpg`` in prod). Alembic's DDL/inspection is synchronous, so
rather than juggle an event loop here we convert the app's async URL to its
sync equivalent and run migrations on a plain sync engine:

    sqlite+aiosqlite://...   -> sqlite://...
    postgresql+asyncpg://... -> postgresql+psycopg://...   (psycopg 3)
    postgresql+psycopg://... -> unchanged
    mysql+aiomysql://...     -> mysql+pymysql://...

This keeps env.py simple and works identically for SQLite (dev/CI) and
Postgres (prod). See docs/migrations.md.

The URL comes from ``get_settings().effective_database_url`` (which honours the
``DATABASE_URL`` env var), so a one-off migration against a throwaway DB is just
``DATABASE_URL=sqlite+aiosqlite:///tmp.db alembic upgrade head``.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import the models module so SQLModel.metadata is fully populated, then expose
# that metadata as the autogenerate target.
from ghostpanel.store import models as _models  # noqa: F401
from sqlmodel import SQLModel

# Alembic Config object (values from alembic.ini).
config = context.config

# Configure Python logging from the ini file, if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for --autogenerate.
target_metadata = SQLModel.metadata


def _sync_url() -> str:
    """Resolve the app DB URL and convert async drivers to sync ones."""
    # An explicit -x url=... or sqlalchemy.url in the ini wins if provided.
    override = config.get_main_option("sqlalchemy.url")
    if override:
        url = override
    else:
        from ghostpanel.server.config import get_settings

        url = get_settings().effective_database_url

    replacements = {
        "sqlite+aiosqlite": "sqlite",
        "postgresql+asyncpg": "postgresql+psycopg",
        "postgres+asyncpg": "postgresql+psycopg",
        "mysql+aiomysql": "mysql+pymysql",
    }
    for async_driver, sync_driver in replacements.items():
        if url.startswith(async_driver + ":"):
            return sync_driver + url[len(async_driver):]
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL against a URL, no DB-API."""
    url = _sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connect and apply against the DB."""
    url = _sync_url()
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # batch mode makes ALTER TABLE work on SQLite (no-op elsewhere).
            render_as_batch=url.startswith("sqlite"),
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
