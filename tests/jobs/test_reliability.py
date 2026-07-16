"""Job reliability tests (W1-A) — reaper, timeout wrapper, dead-letter view.

Offline, temp SQLite per test via the shared ``job_ctx`` fixture. Seeds RUNNING
jobs with a controlled ``locked_at`` to exercise lease expiry deterministically.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from ghostpanel.jobs.reliability import (
    DEFAULT_JOB_TIMEOUT_S,
    DEFAULT_LEASE_S,
    JobTimeout,
    dead_letters,
    reap_stuck_jobs,
    run_with_timeout,
)
from ghostpanel.store import db
from ghostpanel.store.models import JobRow, JobState, _now


async def _seed_running(
    project_id: str,
    *,
    age_seconds: float,
    attempts: int = 1,
    max_attempts: int = 3,
) -> str:
    """Insert a RUNNING job whose lock was taken ``age_seconds`` ago. Returns its id."""
    locked_at = _now() - timedelta(seconds=age_seconds)
    async with db.session_scope() as session:
        job = JobRow(
            project_id=project_id,
            spec={"url": "u"},
            state=JobState.RUNNING,
            attempts=attempts,
            max_attempts=max_attempts,
            locked_by="worker-dead",
            locked_at=locked_at,
            started_at=locked_at,
        )
        session.add(job)
        await session.flush()
        await session.refresh(job)
        return job.id


async def _get(job_id: str) -> JobRow:
    async with db.session_scope() as session:
        job = await session.get(JobRow, job_id)
        assert job is not None
        return job


def test_constants_have_expected_defaults():
    assert DEFAULT_JOB_TIMEOUT_S == 1800
    assert DEFAULT_LEASE_S == 900


async def test_stale_running_with_budget_is_requeued(job_ctx):
    _store, _queue, project_id = job_ctx
    job_id = await _seed_running(project_id, age_seconds=2000, attempts=1, max_attempts=3)

    reaped = await reap_stuck_jobs(lease_seconds=900)
    assert reaped == 1

    job = await _get(job_id)
    assert job.state == JobState.QUEUED
    assert job.locked_by == ""
    assert job.locked_at is None
    assert job.started_at is None
    assert job.attempts == 1  # not bumped by the reaper


async def test_stale_running_at_max_attempts_is_dead_lettered(job_ctx):
    _store, _queue, project_id = job_ctx
    job_id = await _seed_running(project_id, age_seconds=2000, attempts=3, max_attempts=3)

    reaped = await reap_stuck_jobs(lease_seconds=900)
    assert reaped == 1

    job = await _get(job_id)
    assert job.state == JobState.FAILED
    assert job.finished_at is not None
    assert job.locked_at is None
    assert "reaped" in job.error


async def test_fresh_running_job_is_untouched(job_ctx):
    _store, _queue, project_id = job_ctx
    job_id = await _seed_running(project_id, age_seconds=5, attempts=1, max_attempts=3)

    reaped = await reap_stuck_jobs(lease_seconds=900)
    assert reaped == 0

    job = await _get(job_id)
    assert job.state == JobState.RUNNING
    assert job.locked_by == "worker-dead"


async def test_reap_mixed_batch_counts_only_stale(job_ctx):
    _store, _queue, project_id = job_ctx
    stale_retry = await _seed_running(project_id, age_seconds=2000, attempts=1, max_attempts=3)
    stale_dead = await _seed_running(project_id, age_seconds=2000, attempts=3, max_attempts=3)
    fresh = await _seed_running(project_id, age_seconds=1, attempts=1, max_attempts=3)

    reaped = await reap_stuck_jobs(lease_seconds=900)
    assert reaped == 2

    assert (await _get(stale_retry)).state == JobState.QUEUED
    assert (await _get(stale_dead)).state == JobState.FAILED
    assert (await _get(fresh)).state == JobState.RUNNING


async def test_run_with_timeout_raises_on_slow_coro(job_ctx):
    with pytest.raises(JobTimeout):
        await run_with_timeout(asyncio.sleep(10), timeout_s=0.01)


async def test_run_with_timeout_passes_fast_coro_through(job_ctx):
    async def _fast() -> str:
        await asyncio.sleep(0)
        return "ok"

    result = await run_with_timeout(_fast(), timeout_s=5)
    assert result == "ok"


async def test_dead_letters_lists_only_exhausted_failures(job_ctx):
    _store, _queue, project_id = job_ctx
    # A dead-lettered job (FAILED at max_attempts).
    dead_id = await _seed_running(project_id, age_seconds=2000, attempts=3, max_attempts=3)
    await reap_stuck_jobs(lease_seconds=900)
    # A re-queued job (should NOT appear).
    await _seed_running(project_id, age_seconds=2000, attempts=1, max_attempts=3)
    await reap_stuck_jobs(lease_seconds=900)

    letters = await dead_letters()
    assert [j.id for j in letters] == [dead_id]
    assert all(j.state == JobState.FAILED for j in letters)
    assert all(j.attempts >= j.max_attempts for j in letters)


async def test_dead_letters_scoped_by_project(job_ctx):
    _store, _queue, project_id = job_ctx
    await _seed_running(project_id, age_seconds=2000, attempts=3, max_attempts=3)
    await reap_stuck_jobs(lease_seconds=900)

    assert len(await dead_letters(project_id=project_id)) == 1
    assert await dead_letters(project_id="no-such-project") == []
