"""Job reliability helpers (W1-A). Pure functions over ``session_scope`` + models.

Two failure modes that a bare queue cannot handle on its own:

1. **Stuck / orphaned jobs** — a worker claims a job (flips it to ``RUNNING`` with
   ``locked_at``) then dies (crash, OOM, deploy). The row stays ``RUNNING`` forever
   and its ``run`` never completes. ``reap_stuck_jobs`` is a periodic sweep the
   worker loop calls: any ``RUNNING`` job whose lease (``locked_at``) has expired is
   either re-queued for another worker or, once it has burned all its attempts,
   moved to the dead-letter state (``FAILED``).

2. **Runaway jobs** — a single job hangs (a page never settles, a model stalls).
   ``run_with_timeout`` wraps the worker's ``run_job`` so a job cannot occupy a
   worker slot indefinitely; on expiry it raises :class:`JobTimeout`, which the
   worker treats as a normal job failure (retry / dead-letter via the queue).

This module never edits ``queue.py``/``worker.py`` — the orchestrator wires the
reaper interval and the ``run_with_timeout`` wrapper into the worker loop.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta, timezone
from typing import Awaitable, Optional, TypeVar

from sqlalchemy import select

from ghostpanel.store import db
from ghostpanel.store.models import JobRow, JobState, _now

T = TypeVar("T")

# Default wall-clock budget for a single job (30 min). The worker wraps run_job in
# run_with_timeout(..., timeout_s=DEFAULT_JOB_TIMEOUT_S).
DEFAULT_JOB_TIMEOUT_S: int = 1800

# Default lease: a RUNNING job whose lock is older than this is considered orphaned
# (15 min). Kept comfortably above DEFAULT_JOB_TIMEOUT_S is NOT required — the lease
# guards against dead workers, the timeout guards against hung jobs.
DEFAULT_LEASE_S: int = 900


class JobTimeout(Exception):
    """A job exceeded its wall-clock timeout budget in ``run_with_timeout``."""


def _as_utc(dt) -> Optional[object]:
    """Normalize a datetime to a tz-aware UTC value.

    SQLite round-trips ``DateTime`` columns as *naive* strings, so a value written
    tz-aware (via ``models._now``) reads back without tzinfo. Assume UTC for naive
    values so comparisons against a tz-aware ``now`` never raise.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def reap_stuck_jobs(*, lease_seconds: int = DEFAULT_LEASE_S) -> int:
    """Re-queue or dead-letter jobs whose lease has expired.

    A job is stuck when it is ``RUNNING`` and its ``locked_at`` is older than
    ``lease_seconds`` (or missing — an anomalous RUNNING row with no lock). For each
    such job: re-``QUEUE`` it (clear the lock/timestamps) if ``attempts <
    max_attempts``, otherwise mark it ``FAILED`` (dead-letter). ``attempts`` is not
    bumped here — it was already counted at claim time, so a re-queued job is picked
    up with its remaining budget intact.

    Returns the number of jobs reaped (re-queued + dead-lettered).
    """
    now = _now()
    cutoff = now - timedelta(seconds=lease_seconds)
    reaped = 0
    async with db.session_scope() as session:
        rows = (
            await session.execute(
                select(JobRow).where(JobRow.state == JobState.RUNNING)
            )
        ).scalars().all()
        for job in rows:
            locked_at = _as_utc(job.locked_at)
            if locked_at is not None and locked_at >= cutoff:
                continue  # lease still valid — a live worker likely owns it
            if job.attempts < job.max_attempts:
                job.state = JobState.QUEUED
                job.locked_by = ""
                job.locked_at = None
                job.started_at = None
                job.finished_at = None
            else:
                job.state = JobState.FAILED
                job.error = (
                    "reaped: lease expired after "
                    f"{lease_seconds}s with no progress (attempts exhausted)"
                )[:2000]
                job.finished_at = now
                job.locked_by = ""
                job.locked_at = None
            session.add(job)
            reaped += 1
    return reaped


async def run_with_timeout(coro: Awaitable[T], *, timeout_s: float) -> T:
    """Await ``coro`` with a wall-clock budget, raising :class:`JobTimeout` on expiry.

    Thin wrapper over :func:`asyncio.wait_for` that surfaces a job-specific error so
    callers can distinguish a timeout from an arbitrary ``asyncio.TimeoutError``.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_s)
    except (asyncio.TimeoutError, TimeoutError) as exc:
        raise JobTimeout(f"job exceeded timeout of {timeout_s}s") from exc


async def dead_letters(
    project_id: Optional[str] = None, limit: int = 50
) -> list[JobRow]:
    """List dead-lettered jobs: ``FAILED`` and at ``max_attempts`` (budget exhausted).

    Scoped to ``project_id`` when given. Newest first. Powers an ops view of jobs
    that gave up so a human can inspect/replay them.
    """
    async with db.session_scope() as session:
        stmt = select(JobRow).where(
            JobRow.state == JobState.FAILED,
            JobRow.attempts >= JobRow.max_attempts,
        )
        if project_id is not None:
            stmt = stmt.where(JobRow.project_id == project_id)
        stmt = stmt.order_by(
            JobRow.finished_at.desc(), JobRow.created_at.desc(), JobRow.id
        ).limit(limit)
        return list((await session.execute(stmt)).scalars().all())


__all__ = [
    "JobTimeout",
    "reap_stuck_jobs",
    "run_with_timeout",
    "dead_letters",
    "DEFAULT_JOB_TIMEOUT_S",
    "DEFAULT_LEASE_S",
]
