"""Composition seam for the hosted (Phase 2) API.

``register_hosted`` is the single entry point the orchestrator's ``app.py`` calls
to bolt the hosted service onto the existing FastAPI app. It wires the shared
singletons onto ``app.state`` (where ``ghostpanel.auth.deps`` reads them from) and
mounts the ``/v2`` routers.

Import-safe by contract: importing this module must not open a database, read env,
or construct any of the dependencies — all of that is passed in by the caller.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI


def register_hosted(
    app: FastAPI,
    *,
    store: Any,
    queue: Any,
    storage: Any,
    settings: Any,
) -> None:
    """Attach the hosted-product API to ``app``.

    Args:
        app: the FastAPI application to mount onto.
        store: a ``ghostpanel.store.repo.Store`` (data-access layer).
        queue: a ``ghostpanel.jobs.queue.JobQueue`` (durable run queue).
        storage: an ``ArtifactStorage`` implementation.
        settings: the resolved ``ghostpanel.server.config.Settings``.

    The routers read every one of these back off ``app.state`` at request time via
    the ``ghostpanel.auth.deps`` dependencies, so nothing here is captured in a
    closure — swapping ``app.state.store`` in a test is enough to re-point them.
    """
    app.state.store = store
    app.state.queue = queue
    app.state.storage = storage
    app.state.settings = settings

    # Import routers lazily so importing this module never drags in the router
    # (and its transitive auth/store) import graph before the caller wants it.
    from fastapi import Depends

    from ghostpanel.auth.ratelimit import limit_by_ip

    from .routers.account import router as account_router
    from .routers.artifacts import router as artifacts_router
    from .routers.auth import router as auth_router
    from .routers.billing import router as billing_router
    from .routers.members import router as members_router
    from .routers.projects import router as projects_router
    from .routers.runs import router as runs_router

    # Rate-limit the abuse-prone auth surface by client IP in production (per-process;
    # back with Redis for multi-instance — see auth/ratelimit.py). Disabled in dev/test
    # so suites that sign up many users aren't throttled.
    auth_limit = (
        [Depends(limit_by_ip("auth", 10, 60))] if settings.is_production else []
    )
    app.include_router(auth_router, dependencies=auth_limit)
    app.include_router(account_router, dependencies=auth_limit)
    app.include_router(projects_router)
    app.include_router(runs_router)
    app.include_router(billing_router)
    app.include_router(members_router)
    app.include_router(artifacts_router)


__all__ = ["register_hosted"]
