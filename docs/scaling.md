# Scaling Simulation Labs / Ghostpanel

How the hosted backend grows with load, where the real ceiling is, and the order
in which you should reach for bigger infrastructure. The short version, stated up
front so nothing downstream misleads you:

> **The bottleneck is model inference, not our infrastructure.** The durable job
> queue can hand out thousands of jobs per second; a single behavioral run takes
> **minutes** because every persona makes tens of vision-model calls and the whole
> swarm shares one rate limit. Scaling out workers, brokers, and databases buys
> you almost nothing until you raise the model RPM. Read
> [§3 The real ceiling](#3-the-real-ceiling-model-inference-rpm) before you scale
> anything else.

Read alongside:

- [`docs/deploy.md`](./deploy.md) — deployment architecture, process groups, the
  operator production checklist.
- [`docs/deploy-runbook.md`](./deploy-runbook.md) — the deploy pipeline, rollback,
  the first-15-minutes incident checklist.
- [`docs/slos.md`](./slos.md) — the SLOs (enqueue→result, run success) that tell
  you *when* a scaling limit is actually hurting users.
- [`docs/data-policy.md`](./data-policy.md) — retention + sub-processors that bound
  storage growth.
- [`benchmarks/load_test.py`](../benchmarks/load_test.py) — the queue throughput
  harness the numbers below come from.

---

## 1. The architecture, in one diagram

```
  sim CLI / Action / dashboard
        │  POST /v2/runs
        ▼
  API (uvicorn, process group `app`)          ── stateless, N replicas
        │  enqueue → jobs table (Postgres)
        ▼
  durable DB-backed queue  (ghostpanel.jobs.queue.JobQueue)
        │  FairClaim: per-tenant round-robin selection
        ▼
  worker (process group `worker`)             ── STATELESS, N replicas × C slots
        │  one shared headless Chromium + one shared rate-limited Holo client
        │  claim → drive swarm → persist RunReport → publish artifacts
        ▼
  Postgres (runs/jobs/…)  +  object storage (artifacts)
```

Two process groups run off one image ([`fly.toml`](../fly.toml)): `app` serves
public HTTP, `worker` drains the queue and has no inbound service. They scale
independently.

---

## 2. Workers are stateless — scale them horizontally

A worker holds **no durable state of its own**. Everything that matters lives in
Postgres (job + run rows) and object storage (artifacts). A worker is just a loop
that claims a job, drives it, and writes the result back. This is what makes
horizontal scaling safe and boring:

- **Add capacity by adding workers.** Run more `worker` machines, or raise
  `WORKER_CONCURRENCY` (concurrent claim-and-run slots per process — see
  [`server/config.py`](../src/ghostpanel/server/config.py)). Both add claim
  parallelism; neither changes correctness.
- **Claims are atomic across all workers.** On Postgres the queue claims with
  `SELECT … FOR UPDATE SKIP LOCKED`; on SQLite with a guarded
  `UPDATE … WHERE state='queued'` + rowcount check. Two workers racing for the
  same job: exactly one wins, the loser moves on. See
  [`jobs/queue.py`](../src/ghostpanel/jobs/queue.py).
- **Fairness is preserved as you scale.** `FairClaim`
  ([`jobs/scheduler.py`](../src/ghostpanel/jobs/scheduler.py)) hands work out
  round-robin across `project_id`, so one tenant enqueuing 1000 jobs can't starve
  another tenant's 1 job no matter how many workers are running. The rotation
  state is in-memory per worker, but the *claim* is still the same race-safe
  guarded UPDATE — fairness is best-effort, correctness is not.
- **A dead worker loses nothing.** If a worker crashes mid-run, its job stays
  `RUNNING` with a stale `locked_at`. The reaper
  ([`jobs/reliability.py`](../src/ghostpanel/jobs/reliability.py),
  `reap_stuck_jobs`, lease `DEFAULT_LEASE_S` = 900s) re-queues it for another
  worker, or dead-letters it once `attempts` hit `max_attempts`. A per-job
  wall-clock timeout (`run_with_timeout`, `DEFAULT_JOB_TIMEOUT_S` = 1800s) stops a
  single hung page/model from holding a slot forever.
- **SIGINT/SIGTERM drains cleanly.** On a shutdown signal the worker sets a stop
  event, cancels its slots, and closes the shared browser in a `finally` — a
  rolling deploy doesn't strand jobs; whatever was in flight is reaped and
  retried. See `_amain` in [`jobs/worker.py`](../src/ghostpanel/jobs/worker.py).

**Scaling recipe:** more tenants/more runs ⇒ more `worker` machines. There is no
sticky state, no leader, no shard assignment to manage. The only thing you cannot
scale away by adding workers is the model rate limit — next section.

---

## 3. The real ceiling: model inference RPM

This is the honest bottleneck analysis. Everything else in this document is about
infrastructure that is **not** currently the constraint.

### The math

The whole swarm shares **one** rate-limited Holo client (`HAI_RPM`, the hard cap
enforced in [`jobs/worker.py`](../src/ghostpanel/jobs/worker.py) `build_holo_client`).
A persona makes roughly **one vision-model call per step**, and a real flow is
**tens of steps** (~20 is the working estimate used in the load test).

```
free tier:      ~5 RPM shared
calls/persona:  ~20 (one per step)
⇒ per persona:  20 calls ÷ 5 RPM = ~4 minutes of model time
```

A swarm of, say, 8 personas does **not** finish in 4 minutes — all 8 draw from the
same ~5 RPM bucket, so their ~160 total calls serialize on the limiter:
`160 ÷ 5 = ~32 minutes` of wall-clock, regardless of how many worker slots you
give them. Adding workers past the point where they saturate the RPM budget just
produces workers waiting on the rate limiter.

### What raising the tier buys

RPM is the single lever with real leverage. It scales run throughput **linearly**:

| Tier (illustrative) | Shared RPM | ~min / persona | 8-persona swarm wall-clock |
|---------------------|-----------:|---------------:|---------------------------:|
| Free                |          5 |          ~4.0  | ~32 min |
| Paid (e.g. 60)      |         60 |          ~0.3  | ~2.7 min |
| Paid (e.g. 300)     |        300 |          ~0.07 | ~32 s |

(The `PRODUCTION_PLAN.md` Wave A work — a pluggable model interface, per-tenant +
global rate limits, a capacity model mapping RPM → personas → wall-clock — exists
precisely to turn this table into an enforced, per-tier reality and to make the
model vendor swappable so RPM isn't a single-vendor ceiling.)

### The queue is nowhere near the ceiling

[`benchmarks/load_test.py`](../benchmarks/load_test.py) stress-tests **only** the
claim/finalize machinery (the run step is stubbed to an immediate `mark_done` — no
browser, no Holo). It routinely claims-and-finalizes **thousands of jobs per
second** on a throwaway SQLite file, with sub-millisecond-to-low-millisecond
`claim()` latency under contention. Run it yourself:

```bash
python benchmarks/load_test.py --jobs 2000 --concurrency 16
```

The queue will not be the thing that falls over. Given that one real persona run
is ~4 minutes on the free tier, the queue's thousands-per-second headroom means
the DB-backed queue is adequate for a very long time. **Do not** move to a broker
to "scale throughput" — throughput is capped upstream at the model.

---

## 4. When to move off the DB queue → a broker (Redis / NATS)

The DB-backed queue is deliberately the default: no extra moving part, durable,
transactional with the run rows, and — per §3 — far from saturated. Move to a
broker only when you hit a queue-*shaped* limit, not a throughput one:

**Signals it's actually time** (watch these, not vibes):

- `GhostpanelJobBacklogGrowing` / `GhostpanelNoJobCompletions` in
  [`ops/alerts.yml`](../ops/alerts.yml) firing while workers are healthy and the
  RPM budget is *not* the constraint (i.e. you've already raised the tier and
  added workers).
- `claim()` p95 latency climbing under a very high worker count — the guarded
  `UPDATE`/`SKIP LOCKED` contention on the `jobs` table becoming measurable
  (re-run the load test at your real worker count to confirm).
- Postgres write load from queue polling (every idle slot polls every ~2s)
  competing with real query load.
- You want fan-out/pub-sub semantics (live event distribution across many API
  replicas) that a relational table models awkwardly.

**How to move without a rewrite:** the queue is already an abstraction behind
`JobQueue` + `FairClaim`. Introduce a broker-backed implementation that satisfies
the same surface (`enqueue`, `claim`, `attach_run`, `mark_done`, `mark_failed`)
and keep Postgres as the **system of record** for job/run rows — the broker
carries the *ready* signal, the DB carries the *truth*. Concretely:

- **Redis** (Streams + consumer groups): lowest-friction, gives you at-least-once
  delivery and consumer-group claim semantics that map cleanly onto the current
  claim loop. Keep the reaper for lease expiry (Redis `XAUTOCLAIM` or your own).
- **NATS JetStream**: better if you also want durable pub/sub for the live run
  event stream (today `WebSocketHub` is per-process); pulls double duty as the
  event bus.

Keep the `FairClaim` per-tenant round-robin logic — it's queue-implementation
agnostic (it selects *which* tenant's job to take next; the broker just changes
*how* the take is made atomic). And keep dead-lettering + timeouts: a broker does
not remove the need for `reap_stuck_jobs`-style recovery, it just relocates it.

---

## 5. Artifacts: object storage + CDN

Run artifacts (screenshots, `.webm` video, `.wav` audio, `report.*`) are the
largest and fastest-growing data class (see
[`docs/data-policy.md`](./data-policy.md) §1). They already scale independently of
compute:

- **Local disk in dev, S3 in prod** via the `ArtifactStorage` abstraction
  (`STORAGE_BACKEND=s3`). Storage capacity is the provider's problem, not ours.
- **CDN / direct serving.** Set `S3_PUBLIC_BASE_URL`
  ([`server/config.py`](../src/ghostpanel/server/config.py)) to a CDN or bucket
  base URL so artifact links (and report HTML `<img>/<video>` src) resolve to the
  CDN edge instead of round-tripping the API. This offloads large video/image
  bytes from the app process entirely — the app serves JSON, the CDN serves
  pixels. (Note: per the Wave-0 IDOR fix, tenant-scoped artifacts are served
  through an authed proxy + short-lived signed URLs; a public CDN base is for
  content that is safe to serve by unguessable URL — reconcile the two before
  flipping a bucket public.)
- **Growth is bounded by retention.** `ops/retention.py` deletes artifacts + their
  `RunRow` after 90 days (default; per-tenant negotiable). Storage grows linearly
  with run volume and is capped by the retention window, not unbounded.
- **Multi-region storage** is a bucket-configuration concern (cross-region
  replication / a multi-region bucket) — no app change; artifacts are addressed by
  `<run_id>/…` key and the storage backend resolves the region.

---

## 6. Database scaling

Postgres holds the queue and all run/account metadata. It scales the usual way,
in this order:

1. **Connection pooling first.** Many worker slots + API replicas ⇒ many
   connections. Put **PgBouncer** (transaction pooling) in front of Postgres
   before you scale the instance — the async SQLAlchemy engine opens a pool per
   process, and replica count multiplies that. This is the cheapest, highest-yield
   database change.
2. **Vertical, then read-replicas.** Scale the primary up first (it's simplest and
   often enough given the inference-bound workload). When read load (dashboard
   history, trends, heatmaps) starts competing with write load, add **read
   replicas** and route read-only queries there. Keep **all queue operations**
   (`claim`, `mark_*`) on the **primary** — `SELECT … FOR UPDATE SKIP LOCKED` and
   the guarded UPDATE are writes and must not hit a replica, and reading queue
   state from a lagging replica would break claim fairness/correctness.
3. **Partition/prune the big tables.** `runs` (with embedded `report_json`) and
   `jobs` grow with volume; retention (`ops/retention.py`) prunes `runs`, and old
   `jobs` age out too. If they still get large, partition by time.
4. **Backups scale with the DB.** `ops/backup.sh` does a logical `pg_dump`; for a
   large DB move to the provider's snapshot/PITR and keep `restore.sh` drills
   honest (see [`docs/data-policy.md`](./data-policy.md) §2 and the deploy
   checklist).

---

## 7. Multi-region considerations

Single-region (`primary_region = "iad"` in [`fly.toml`](../fly.toml)) is the right
default and covers a long runway. Reach for multi-region only under specific
pressure, and know the trade-offs:

- **Latency to the API/dashboard** — the easy win. The API is stateless; run
  `app` replicas in multiple regions behind anycast and they all talk to one
  primary DB. Read replicas per region cut read latency (§6).
- **The database is the hard part.** A single primary means cross-region workers
  pay write latency on every `claim`/`mark_*`. Options, worst-to-best effort:
  keep the primary central and accept the latency (fine while inference-bound —
  a few ms of DB latency is noise against a 4-minute run); regional read replicas
  with writes home-run to the primary; full multi-primary only if you shard
  tenants by region (large project — don't until forced).
- **Artifact/data residency.** EU-customer artifacts (screenshots of real flows —
  regulated data, see [`docs/data-policy.md`](./data-policy.md)) may need to stay
  in an EU bucket + EU workers. This is a compliance driver, not a performance
  one, and is the most likely *real* reason you'd go multi-region.
- **Workers follow the DB and the data.** Because a worker is stateless, placing
  workers in a region is just "which DB + which bucket does this worker group
  talk to." No code change — configuration.

**Bottom line:** multi-region is driven by data residency and API latency, almost
never by throughput — throughput is bounded by RPM (§3), and RPM is raised by
tier, not geography.

---

## 8. Scaling checklist (what to reach for, in order)

1. Runs too slow / swarm wall-clock too high → **raise `HAI_RPM` (paid tier)**.
   This is the only lever that moves the real bottleneck. (§3)
2. RPM raised and jobs still backing up → **add `worker` machines / raise
   `WORKER_CONCURRENCY`** until workers saturate the RPM budget. (§2)
3. Many workers + connection errors → **PgBouncer** in front of Postgres. (§6.1)
4. Read load (dashboards/trends) competing with writes → **read replicas**, reads
   only, queue stays on primary. (§6.2)
5. Artifact bytes loading the app / slow media → **`S3_PUBLIC_BASE_URL` CDN**. (§5)
6. Queue-shaped limits (claim latency, backlog with healthy workers *and* ample
   RPM) → **broker (Redis/NATS)** behind the same `JobQueue` surface. (§4)
7. Data residency / API-latency-by-geography → **multi-region**. (§7)

Steps 1–2 cover essentially all real growth. Steps 3–7 are for scale most
deployments will not reach while the product is inference-bound.
