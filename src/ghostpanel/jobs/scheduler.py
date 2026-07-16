"""Per-tenant fair scheduling on top of the durable ``JobQueue`` (INF-B).

``JobQueue.claim`` is strictly oldest-first. That is fine for a single tenant,
but the shared model RPM is the scarce resource for the whole swarm: if tenant A
enqueues 1000 jobs and tenant B enqueues 1, strict FIFO drains all of A before B
ever runs. ``FairClaim`` sits in front of the queue and hands work out
**round-robin across ``project_id``** so no tenant can starve the others.

Design (pure Python over the queue's reads + the same guarded UPDATE the queue
uses — ``queue.py`` is NOT modified):

1. Read the set of projects that currently have QUEUED jobs, together with the
   oldest ``created_at`` in each project's backlog (one grouped SELECT).
2. Order those candidate projects by a deterministic *fair* key:
   ``(last_served_seq, oldest_created_at, project_id)`` ascending — i.e. the
   least-recently-served project first, breaking ties by the older backlog and
   then by id. A project that has never been served sorts before every served
   one (sentinel ``-1``). ``last_served_seq`` is a monotonic counter kept
   in-memory on the ``FairClaim`` instance and bumped each time we hand out a
   job for a project, which produces the round-robin rotation.
3. Walk the ordered candidates and try to atomically take that project's oldest
   QUEUED job with a guarded ``UPDATE ... WHERE id=:id AND state='queued'``
   scoped to the project (rowcount==1 ⇒ we won; 0 ⇒ another worker took it, so
   move to the next candidate). This is the identical race-safe technique
   ``JobQueue._claim_guarded`` uses, just narrowed to a chosen project.

The claim stays atomic across concurrent workers: two workers may pick the same
project and even the same oldest job, but only one guarded UPDATE flips it to
RUNNING; the loser observes ``rowcount == 0`` and retries the next candidate.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError

from ghostpanel.jobs.queue import JobQueue
from ghostpanel.store import db
from ghostpanel.store.models import JobRow, JobState, _now

# Sentinel serve sequence for a project we have never handed a job to; sorts
# before any real (>= 0) serve counter so unseen tenants get picked up first.
_NEVER_SERVED = -1

# Bound the retry passes when every candidate loses its guarded UPDATE race
# (pure contention). Each pass re-reads the live candidate set.
_MAX_PASSES = 200


class FairClaim:
    """Fair, per-tenant round-robin wrapper around :class:`JobQueue`.

    Construct with the shared ``JobQueue`` and call :meth:`claim`. All other
    queue operations (enqueue, mark_done, …) go straight to ``queue``; only the
    *selection* of which job to claim is made fair here.
    """

    def __init__(self, queue: JobQueue) -> None:
        self.queue = queue
        # project_id -> monotonic sequence number of when it was last served.
        self._last_served: dict[str, int] = {}
        # Monotonic tick incremented every time a project is served.
        self._serve_seq: int = 0

    async def claim(self, worker_id: str) -> Optional[JobRow]:
        """Claim the oldest QUEUED job of the least-recently-served project.

        Returns the claimed :class:`JobRow` (now RUNNING, locked by
        ``worker_id``), or ``None`` when no project has a QUEUED job. Atomic
        across concurrent workers.
        """
        for _pass in range(_MAX_PASSES):
            candidates = await self._candidate_projects()
            if not candidates:
                return None

            # Deterministic fair order: least-recently-served first, then the
            # older backlog, then project_id for a stable tie-break.
            ordered = sorted(
                candidates,
                key=lambda c: (
                    self._last_served.get(c[0], _NEVER_SERVED),
                    c[1],
                    c[0],
                ),
            )

            for project_id, _oldest in ordered:
                job = await self._claim_from_project(project_id, worker_id)
                if job is not None:
                    self._mark_served(project_id)
                    return job
                # rowcount 0 / project drained under us: try next candidate.

            # Every candidate lost its race this pass — re-read and retry.
        return None

    def _mark_served(self, project_id: str) -> None:
        """Record that ``project_id`` was just served, advancing the rotation."""
        self._last_served[project_id] = self._serve_seq
        self._serve_seq += 1

    async def _candidate_projects(self) -> list[tuple[str, _dt.datetime]]:
        """Projects with >=1 QUEUED job and their oldest queued ``created_at``.

        One grouped SELECT via ``session_scope`` (read-only) — never touches
        ``queue.py``.
        """
        async with db.session_scope() as session:
            stmt = (
                select(JobRow.project_id, func.min(JobRow.created_at))
                .where(JobRow.state == JobState.QUEUED)
                .group_by(JobRow.project_id)
            )
            rows = (await session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]

    async def _claim_from_project(
        self, project_id: str, worker_id: str
    ) -> Optional[JobRow]:
        """Atomically take ``project_id``'s oldest QUEUED job → RUNNING.

        Same guarded-UPDATE technique as ``JobQueue._claim_guarded`` but scoped
        to one project: pick the oldest QUEUED id for the project, then flip it
        with ``UPDATE ... WHERE id=:id AND state='queued'``. ``rowcount == 1``
        means we won the race and return the row; ``0`` means another worker
        beat us (return ``None`` so the caller tries the next project). Retries
        transient SQLite ``database is locked`` errors.
        """
        now = _now()
        for _attempt in range(100):
            try:
                async with db.session_scope() as session:
                    row = (
                        await session.execute(
                            select(JobRow.id)
                            .where(
                                JobRow.state == JobState.QUEUED,
                                JobRow.project_id == project_id,
                            )
                            .order_by(JobRow.created_at, JobRow.id)
                            .limit(1)
                        )
                    ).first()
                    if row is None:
                        return None
                    job_id = row[0]
                    result = await session.execute(
                        update(JobRow)
                        .where(
                            JobRow.id == job_id,
                            JobRow.state == JobState.QUEUED,
                        )
                        .values(
                            state=JobState.RUNNING,
                            locked_by=worker_id,
                            locked_at=now,
                            started_at=now,
                            attempts=JobRow.attempts + 1,
                        )
                    )
                    if result.rowcount == 1:
                        return (
                            await session.execute(
                                select(JobRow)
                                .where(JobRow.id == job_id)
                                .execution_options(populate_existing=True)
                            )
                        ).scalars().first()
                    # Lost the race for this job; another worker took it. The
                    # project may still have other QUEUED jobs, so loop and pick
                    # the next oldest for this project.
            except OperationalError:
                await asyncio.sleep(0.05)
        return None


__all__ = ["FairClaim"]
