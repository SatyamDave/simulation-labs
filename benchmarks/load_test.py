"""Load test for the durable job queue (Phase 5, P5-D).

What this measures — and what it deliberately does NOT.
------------------------------------------------------
Ghostpanel's hosted backend runs swarms through a durable, DB-backed queue
(`ghostpanel.jobs.queue.JobQueue`). A pool of `WORKER_CONCURRENCY` worker slots
each loops: `claim()` the oldest QUEUED job atomically, drive it, then
`mark_done()`. This script stress-tests exactly that claim/finalize machinery —
the contended part — under concurrency, on a throwaway SQLite database.

It does NOT launch a browser or call Holo. The real run step
(`ghostpanel.jobs.worker.run_job`) is replaced by an immediate `mark_done`, so
what we time is purely the queue: how fast N jobs can be atomically claimed and
finalized by C concurrent workers, and how long each `claim()` call takes under
write contention (on SQLite, the guarded `UPDATE ... WHERE state='queued'`
retry path; on Postgres this would be `SELECT ... FOR UPDATE SKIP LOCKED`).

The honest caveat, printed in the summary: **real end-to-end throughput is not
bounded by the queue.** It is bounded by the shared Holo rate limit
(`HAI_RPM`, ~5 requests/min on the free tier) times the number of Holo calls a
persona makes to finish a flow (~one per step, tens of steps). A single real
persona run therefore takes minutes; the queue can hand out thousands of jobs a
second. The queue is never the bottleneck — the model API is. This test proves
the queue won't be the thing that falls over, and quantifies its headroom.

No network. No external services. Deterministic.

Run:
    python benchmarks/load_test.py --jobs 200 --concurrency 8
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
import time
from pathlib import Path

from ghostpanel.jobs.queue import JobQueue
from ghostpanel.server.config import get_settings
from ghostpanel.store import db
from ghostpanel.store.models import JobState, Project, User


# --------------------------------------------------------------------------- setup
async def _seed_project() -> str:
    """Insert one real user + project so enqueued jobs satisfy the FK, and
    return the project id. Keeps the test honest even if FK enforcement is on."""
    async with db.session_scope() as session:
        user = User(email="loadtest@example.com", password_hash="x")
        session.add(user)
        await session.flush()
        project = Project(name="load-test", owner_id=user.id)
        session.add(project)
        await session.flush()
        return project.id


async def _enqueue_all(queue: JobQueue, project_id: str, jobs: int) -> float:
    """Insert `jobs` synthetic QUEUED jobs. Returns wall seconds for the insert."""
    t0 = time.perf_counter()
    for i in range(jobs):
        await queue.enqueue(
            project_id,
            {
                "url": "https://example.test/signup",
                "task": "synthetic load-test job (no browser, no Holo)",
                "persona_ids": ["power-user"],
                "flow_name": f"load-{i}",
            },
        )
    return time.perf_counter() - t0


# --------------------------------------------------------------------------- drain
async def _drain_worker(
    queue: JobQueue,
    worker_id: str,
    claim_latencies: list[float],
    counters: dict[str, int],
) -> None:
    """One concurrency slot: claim → (STUBBED run) → mark_done, until the queue
    is drained. The run step is replaced by an immediate mark_done so we measure
    the QUEUE, not a swarm."""
    while True:
        t0 = time.perf_counter()
        job = await queue.claim(worker_id)
        claim_latencies.append(time.perf_counter() - t0)
        if job is None:
            # No QUEUED jobs remain (all jobs are enqueued before draining, so an
            # empty claim means the queue is truly drained for this slot).
            return
        # --- STUB: real worker would drive the swarm here (run_job). We don't
        #     launch chromium or call Holo — mark the job done immediately so the
        #     measurement isolates the queue's claim/finalize path.
        await queue.mark_done(job.id)
        counters["done"] += 1


async def _run(jobs: int, concurrency: int) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="sl-loadtest-")) / "loadtest.db"
    engine = db.make_engine(f"sqlite+aiosqlite:///{tmp}")
    db.set_engine(engine)
    try:
        await db.init_db()
        project_id = await _seed_project()
        queue = JobQueue()

        enqueue_s = await _enqueue_all(queue, project_id, jobs)

        claim_latencies: list[float] = []
        counters = {"done": 0}

        drain_t0 = time.perf_counter()
        await asyncio.gather(
            *(
                _drain_worker(queue, f"w#{i}", claim_latencies, counters)
                for i in range(concurrency)
            )
        )
        drain_s = time.perf_counter() - drain_t0

        # Sanity: every job should be DONE.
        from sqlmodel import select

        from ghostpanel.store.models import JobRow

        async with db.session_scope() as session:
            rows = (
                await session.exec(
                    select(JobRow.id).where(JobRow.state == JobState.DONE)
                )
            ).all()
            done_in_db = len(rows)

        return {
            "jobs": jobs,
            "concurrency": concurrency,
            "enqueue_s": enqueue_s,
            "drain_s": drain_s,
            "done": counters["done"],
            "done_in_db": int(done_in_db),
            "claims_per_sec": jobs / drain_s if drain_s > 0 else float("inf"),
            "enqueue_per_sec": jobs / enqueue_s if enqueue_s > 0 else float("inf"),
            "claim_latencies_ms": sorted(x * 1000 for x in claim_latencies),
            "total_claim_calls": len(claim_latencies),
        }
    finally:
        await engine.dispose()
        db.set_engine(None)


# --------------------------------------------------------------------------- report
def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(round(p * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def _print_report(r: dict) -> None:
    lat = r["claim_latencies_ms"]
    settings = get_settings()
    rpm = settings.hai_rpm
    steps_per_run = 20  # a persona makes ~1 Holo call per step; tens of steps/flow
    seconds_per_run = steps_per_run / rpm * 60 if rpm > 0 else float("inf")

    line = "=" * 66
    print()
    print(line)
    print("  Ghostpanel queue load test — claim/finalize throughput")
    print(line)
    print(f"  {'jobs':<26}{r['jobs']:>12}")
    print(f"  {'concurrency (worker slots)':<26}{r['concurrency']:>12}")
    print(f"  {'enqueue wall time (s)':<26}{r['enqueue_s']:>12.3f}")
    print(f"  {'drain wall time (s)':<26}{r['drain_s']:>12.3f}")
    print(f"  {'jobs done':<26}{r['done']:>12}")
    print(f"  {'jobs DONE in DB':<26}{r['done_in_db']:>12}")
    print(f"  {'enqueue rate (jobs/s)':<26}{r['enqueue_per_sec']:>12.1f}")
    print(f"  {'CLAIM THROUGHPUT (claims/s)':<26}{r['claims_per_sec']:>12.1f}")
    print(line)
    print("  claim() latency under contention")
    print(f"  {'claim calls (incl. empty)':<26}{r['total_claim_calls']:>12}")
    print(f"  {'p50 (ms)':<26}{_pct(lat, 0.50):>12.3f}")
    print(f"  {'p95 (ms)':<26}{_pct(lat, 0.95):>12.3f}")
    print(f"  {'max (ms)':<26}{_pct(lat, 1.0):>12.3f}")
    print(line)
    ok = r["done"] == r["jobs"] and r["done_in_db"] == r["jobs"]
    print(f"  correctness: all {r['jobs']} jobs claimed exactly once & DONE: "
          f"{'PASS' if ok else 'FAIL'}")
    print(line)
    print("  HONEST NOTE — the queue is not the real bottleneck.")
    print("  This measures ONLY queue machinery: the run step is stubbed")
    print("  (mark_done immediately, no browser, no Holo). Real end-to-end")
    print(f"  throughput is bounded by the shared Holo cap (~{rpm:.0f} RPM) times")
    print(f"  the ~{steps_per_run} Holo calls a persona makes per flow — i.e. one real")
    print(f"  persona run takes ~{seconds_per_run/60:.1f} min, and a swarm shares that")
    print("  one rate limiter. The queue hands out thousands of jobs a second;")
    print("  the model API, not the queue, sets real swarm wall-clock.")
    print(line)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load-test the Ghostpanel durable job queue (no network)."
    )
    parser.add_argument("--jobs", type=int, default=200,
                        help="number of synthetic jobs to enqueue (default 200)")
    parser.add_argument("--concurrency", type=int, default=8,
                        help="concurrent worker slots draining the queue (default 8)")
    args = parser.parse_args()

    if args.jobs < 1 or args.concurrency < 1:
        parser.error("--jobs and --concurrency must both be >= 1")

    result = asyncio.run(_run(args.jobs, args.concurrency))
    _print_report(result)


if __name__ == "__main__":
    main()
