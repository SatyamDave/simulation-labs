"""JobQueue (P2-D) tests — durable DB-backed queue semantics, offline.

Written against the FROZEN ``JobQueue`` interface. While ``jobs/queue.py`` is a
stub (methods raise ``NotImplementedError``) every test is xfailed via
``strict=False`` so the suite stays green; the moment P2-D fills the bodies the
guard flips off and these run for real (an xpass is tolerated by strict=False).
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from ghostpanel.jobs.queue import JobQueue
from ghostpanel.store.models import JobState


def _is_stub(fn) -> bool:
    try:
        return "NotImplementedError" in inspect.getsource(fn)
    except (OSError, TypeError):
        return False


_QUEUE_STUBBED = _is_stub(JobQueue.enqueue)

pytestmark = pytest.mark.xfail(
    _QUEUE_STUBBED,
    reason="jobs.queue.JobQueue still a stub (P2-D not landed)",
    strict=False,
)


async def test_enqueue_creates_queued_job(job_ctx):
    _store, queue, project_id = job_ctx
    job = await queue.enqueue(project_id, {"url": "u", "task": "t"})
    assert job.state == JobState.QUEUED
    assert job.project_id == project_id

    fetched = await queue.get_job(job.id)
    assert fetched is not None and fetched.id == job.id


async def test_claim_empty_queue_returns_none(job_ctx):
    _store, queue, _project_id = job_ctx
    assert await queue.claim("worker-1") is None


async def test_two_concurrent_claims_get_distinct_jobs(job_ctx):
    _store, queue, project_id = job_ctx
    j1 = await queue.enqueue(project_id, {"n": 1})
    j2 = await queue.enqueue(project_id, {"n": 2})

    a, b = await asyncio.gather(queue.claim("worker-A"), queue.claim("worker-B"))
    claimed = [j for j in (a, b) if j is not None]
    assert len(claimed) == 2
    assert {j.id for j in claimed} == {j1.id, j2.id}  # distinct, no double-claim
    for job in claimed:
        assert job.state == JobState.RUNNING

    # Queue now drained.
    assert await queue.claim("worker-C") is None


async def test_mark_done_transitions_to_done(job_ctx):
    _store, queue, project_id = job_ctx
    job = await queue.enqueue(project_id, {"url": "u"})
    claimed = await queue.claim("worker-1")
    assert claimed is not None and claimed.id == job.id

    await queue.mark_done(job.id)
    done = await queue.get_job(job.id)
    assert done.state == JobState.DONE


async def test_mark_failed_no_retry_transitions_to_failed(job_ctx):
    _store, queue, project_id = job_ctx
    job = await queue.enqueue(project_id, {"url": "u"})
    await queue.claim("worker-1")

    await queue.mark_failed(job.id, "boom", retry=False)
    failed = await queue.get_job(job.id)
    assert failed.state == JobState.FAILED
    assert "boom" in failed.error


async def test_retry_requeues_until_max_attempts_then_failed(job_ctx):
    _store, queue, project_id = job_ctx
    job = await queue.enqueue(project_id, {"url": "u"})
    assert job.max_attempts == 3

    # attempt 1: claim (attempts -> 1), fail with retry -> back to QUEUED
    c1 = await queue.claim("w")
    assert c1 is not None
    await queue.mark_failed(job.id, "err-1", retry=True)
    assert (await queue.get_job(job.id)).state == JobState.QUEUED

    # attempt 2: same again -> still retryable
    c2 = await queue.claim("w")
    assert c2 is not None
    await queue.mark_failed(job.id, "err-2", retry=True)
    assert (await queue.get_job(job.id)).state == JobState.QUEUED

    # attempt 3: attempts now hits max_attempts -> FAILED, no requeue
    c3 = await queue.claim("w")
    assert c3 is not None
    await queue.mark_failed(job.id, "err-3", retry=True)
    final = await queue.get_job(job.id)
    assert final.state == JobState.FAILED
    assert await queue.claim("w") is None  # not requeued


async def test_attach_run_links_run_id(job_ctx):
    _store, queue, project_id = job_ctx
    job = await queue.enqueue(project_id, {"url": "u"})
    await queue.attach_run(job.id, "run-xyz")
    assert (await queue.get_job(job.id)).run_id == "run-xyz"


async def test_list_jobs_scoped_to_project(job_ctx):
    _store, queue, project_id = job_ctx
    await queue.enqueue(project_id, {"n": 1})
    await queue.enqueue(project_id, {"n": 2})
    jobs = await queue.list_jobs(project_id)
    assert len(jobs) == 2
    assert all(j.project_id == project_id for j in jobs)
