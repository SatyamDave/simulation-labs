"""FairClaim (INF-B) tests — per-tenant fair-share scheduling, offline.

Verifies that ``FairClaim`` hands jobs out round-robin across ``project_id``
(so a tenant with a huge backlog can't starve others) and that concurrent
claims never double-claim a job. Uses a fresh temp SQLite DB with three seeded
tenants A(5) / B(2) / C(1).
"""

from __future__ import annotations

import asyncio

import pytest

from ghostpanel.jobs.queue import JobQueue
from ghostpanel.jobs.scheduler import FairClaim
from ghostpanel.store import db
from ghostpanel.store.models import JobState


@pytest.fixture
async def tenants_ctx(tmp_path):
    """Temp DB with 3 projects (tenants) each holding a QUEUED backlog.

    Yields ``(queue, {"A": pid, "B": pid, "C": pid}, backlog_counts)``. Jobs are
    enqueued A-first, then B, then C so ``created_at`` is deterministic.
    """
    from ghostpanel.store.repo import Store

    engine = db.make_engine(f"sqlite+aiosqlite:///{tmp_path / 'sched.db'}")
    db.set_engine(engine)
    await db.init_db(engine)

    store = Store()
    queue = JobQueue()

    counts = {"A": 5, "B": 2, "C": 1}
    project_ids: dict[str, str] = {}
    for label, n in counts.items():
        user = await store.create_user(f"{label}@example.com", "hash")
        project = await store.create_project(owner=user, name=f"Tenant {label}")
        project_ids[label] = project.id
        for i in range(n):
            await queue.enqueue(project.id, {"label": label, "n": i})

    try:
        yield queue, project_ids, counts
    finally:
        db.set_engine(None)
        await engine.dispose()


async def test_round_robin_does_not_drain_one_tenant(tenants_ctx):
    """Claims rotate across tenants; A(5) is never drained before B/C run."""
    queue, project_ids, counts = tenants_ctx
    fair = FairClaim(queue)
    id_to_label = {pid: label for label, pid in project_ids.items()}

    served: list[str] = []
    while True:
        job = await fair.claim("worker-1")
        if job is None:
            break
        assert job.state == JobState.RUNNING
        served.append(id_to_label[job.project_id])

    total = sum(counts.values())
    assert len(served) == total, "every queued job should eventually be claimed"

    # The first three claims must hit all three distinct tenants — proof that a
    # backlog-heavy tenant does not get served twice before the others get once.
    assert set(served[:3]) == {"A", "B", "C"}

    # Strong fair-share invariant: replay the sequence and require that at each
    # step the served tenant had the *minimum* served-so-far count among tenants
    # that still had a backlog at that moment (ties allowed).
    remaining = dict(counts)
    served_so_far = {label: 0 for label in counts}
    for label in served:
        eligible = [lbl for lbl, rem in remaining.items() if rem > 0]
        min_served = min(served_so_far[lbl] for lbl in eligible)
        assert served_so_far[label] == min_served, (
            f"tenant {label} served out of fair order: "
            f"served_so_far={served_so_far}, remaining={remaining}"
        )
        served_so_far[label] += 1
        remaining[label] -= 1

    # And concretely: A is NOT drained first.
    assert served[:5] != ["A", "A", "A", "A", "A"]


async def test_concurrent_claims_are_distinct_no_double_claim(tenants_ctx):
    """gather() of N claims yields N distinct jobs (atomic guarded UPDATE)."""
    queue, _project_ids, counts = tenants_ctx
    fair = FairClaim(queue)
    total = sum(counts.values())

    results = await asyncio.gather(
        *(fair.claim(f"worker-{i}") for i in range(total))
    )
    claimed = [j for j in results if j is not None]

    assert len(claimed) == total, "all jobs claimed exactly once"
    job_ids = {j.id for j in claimed}
    assert len(job_ids) == total, "no job claimed twice (no double-claim)"
    assert all(j.state == JobState.RUNNING for j in claimed)

    # Queue fully drained: further claims see nothing.
    assert await fair.claim("worker-extra") is None


async def test_more_workers_than_jobs_get_none(tenants_ctx):
    """Extra concurrent workers beyond the backlog get None, not stale jobs."""
    queue, _project_ids, counts = tenants_ctx
    fair = FairClaim(queue)
    total = sum(counts.values())

    results = await asyncio.gather(
        *(fair.claim(f"worker-{i}") for i in range(total + 4))
    )
    claimed = [j for j in results if j is not None]
    assert len(claimed) == total
    assert {j.id for j in claimed}.__len__() == total


async def test_empty_queue_returns_none(tmp_path):
    """No queued jobs anywhere → claim returns None."""
    engine = db.make_engine(f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")
    db.set_engine(engine)
    await db.init_db(engine)
    try:
        fair = FairClaim(JobQueue())
        assert await fair.claim("worker-1") is None
    finally:
        db.set_engine(None)
        await engine.dispose()
