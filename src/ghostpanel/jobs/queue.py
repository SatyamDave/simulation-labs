"""Durable, DB-backed job queue. Agent P2-D. Signatures FROZEN.

No Redis: jobs live in the ``jobs`` table. ``claim`` must be atomic across
concurrent workers — on Postgres use ``SELECT ... FOR UPDATE SKIP LOCKED``; on
SQLite a short transaction that flips the oldest QUEUED row to RUNNING with a
guarded UPDATE (rowcount check). Every method uses ``store.db.session_scope``.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from ghostpanel.store import db
from ghostpanel.store.models import JobRow, JobState, _now


class JobQueue:
    """Enqueue + claim + finalize swarm jobs."""

    async def enqueue(self, project_id: str, spec: dict[str, Any]) -> JobRow:
        """Insert a QUEUED job. ``spec`` = {url, task, persona_ids, flow_name,
        fixture, rpm}. Returns the row."""
        async with db.session_scope() as session:
            job = JobRow(
                project_id=project_id,
                spec=dict(spec or {}),
                state=JobState.QUEUED,
            )
            session.add(job)
            await session.flush()
            await session.refresh(job)
        return job

    async def claim(self, worker_id: str) -> Optional[JobRow]:
        """Atomically take the oldest QUEUED job → RUNNING (locked_by=worker_id,
        started_at=now, attempts+=1). Return it, or None if the queue is empty."""
        dialect = db.get_engine().dialect.name
        if dialect == "postgresql":
            return await self._claim_postgres(worker_id)
        return await self._claim_guarded(worker_id)

    async def _claim_postgres(self, worker_id: str) -> Optional[JobRow]:
        """Postgres path: row-level lock + SKIP LOCKED means a single transaction
        both selects and updates the oldest unlocked QUEUED row with no race."""
        async with db.session_scope() as session:
            stmt = (
                select(JobRow)
                .where(JobRow.state == JobState.QUEUED)
                .order_by(JobRow.created_at, JobRow.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job = (await session.execute(stmt)).scalars().first()
            if job is None:
                return None
            self._mark_claimed(job, worker_id)
            session.add(job)
            await session.flush()
            await session.refresh(job)
            return job

    async def _claim_guarded(self, worker_id: str) -> Optional[JobRow]:
        """SQLite path: no SKIP LOCKED, so we pick the oldest QUEUED id then flip it
        with a guarded ``UPDATE ... WHERE id=:id AND state='queued'``. rowcount==1
        means we won the race; 0 means another worker took it first — retry with the
        next candidate. Also retries transient ``database is locked`` errors."""
        now = _now()
        for _attempt in range(100):
            try:
                async with db.session_scope() as session:
                    row = (
                        await session.execute(
                            select(JobRow.id)
                            .where(JobRow.state == JobState.QUEUED)
                            .order_by(JobRow.created_at, JobRow.id)
                            .limit(1)
                        )
                    ).first()
                    if row is None:
                        return None
                    job_id = row[0]
                    result = await session.execute(
                        update(JobRow)
                        .where(JobRow.id == job_id, JobRow.state == JobState.QUEUED)
                        .values(
                            state=JobState.RUNNING,
                            locked_by=worker_id,
                            locked_at=now,
                            started_at=now,
                            attempts=JobRow.attempts + 1,
                        )
                    )
                    if result.rowcount == 1:
                        job = (
                            await session.execute(
                                select(JobRow)
                                .where(JobRow.id == job_id)
                                .execution_options(populate_existing=True)
                            )
                        ).scalars().first()
                        return job
                    # Lost the race for this candidate; loop and try the next one.
            except OperationalError:
                # SQLite write contention ("database is locked"): back off, retry.
                await asyncio.sleep(0.05)
        return None

    @staticmethod
    def _mark_claimed(job: JobRow, worker_id: str) -> None:
        now = _now()
        job.state = JobState.RUNNING
        job.locked_by = worker_id
        job.locked_at = now
        job.started_at = now
        job.attempts += 1

    async def attach_run(self, job_id: str, run_id: str) -> None:
        """Link the created run to the job (sets JobRow.run_id)."""
        async with db.session_scope() as session:
            job = await session.get(JobRow, job_id)
            if job is None:
                return
            job.run_id = run_id
            session.add(job)

    async def mark_done(self, job_id: str) -> None:
        async with db.session_scope() as session:
            job = await session.get(JobRow, job_id)
            if job is None:
                return
            job.state = JobState.DONE
            job.finished_at = _now()
            job.locked_by = ""
            job.locked_at = None
            session.add(job)

    async def mark_failed(self, job_id: str, error: str, *, retry: bool = True) -> None:
        """FAILED, or re-QUEUE when retry and attempts < max_attempts."""
        async with db.session_scope() as session:
            job = await session.get(JobRow, job_id)
            if job is None:
                return
            job.error = (error or "")[:2000]
            if retry and job.attempts < job.max_attempts:
                # Back to the queue for another worker (attempts already counted at
                # claim time, so this naturally caps at max_attempts total tries).
                job.state = JobState.QUEUED
                job.locked_by = ""
                job.locked_at = None
                job.started_at = None
                job.finished_at = None
            else:
                job.state = JobState.FAILED
                job.finished_at = _now()
                job.locked_by = ""
                job.locked_at = None
            session.add(job)

    async def get_job(self, job_id: str) -> Optional[JobRow]:
        async with db.session_scope() as session:
            return await session.get(JobRow, job_id)

    async def list_jobs(self, project_id: str, *, limit: int = 50) -> list[JobRow]:
        async with db.session_scope() as session:
            stmt = (
                select(JobRow)
                .where(JobRow.project_id == project_id)
                .order_by(JobRow.created_at.desc(), JobRow.id)
                .limit(limit)
            )
            return list((await session.execute(stmt)).scalars().all())


__all__ = ["JobQueue"]
