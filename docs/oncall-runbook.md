# On-call runbook

One entry per alert in [`ops/alerts.yml`](../ops/alerts.yml): what it means, first
response, which signals to check, and when to escalate. Each alert protects an SLO
in [`docs/slos.md`](./slos.md); the deploy/rollback mechanics referenced below live
in [`docs/deploy-runbook.md`](./deploy-runbook.md). For declaring and running an
incident (severities, comms, roles, postmortem), see
[`docs/incident-response.md`](./incident-response.md).

## How to use this

- **`severity: page`** → wake someone; treat as a potential incident (open the
  [incident flow](./incident-response.md)).
- **`severity: ticket`** → file it, triage within the business day; a budget is
  burning but users are (probably) not down yet.
- **First move on any `page` that correlates with a deploy: roll back first,
  diagnose later** ([deploy-runbook §Rollback](./deploy-runbook.md#rollback)).
- **The golden signals** everywhere below:
  - `curl -i $PROD_BASE_URL/healthz` — liveness (process up?)
  - `curl -i $PROD_BASE_URL/readyz` — readiness (DB reachable?)
  - `flyctl status --app simulation-labs` / `flyctl logs --app simulation-labs`
  - `flyctl logs --app simulation-labs --group worker` — the **worker**, which the
    API health checks do **not** cover.
  - `/metrics` (Prometheus) — the series each alert keys on.

### Dashboards to keep open

There is no bundled Grafana JSON; these are the panels to build from the
[`/metrics`](../src/ghostpanel/server/metrics.py) series (names are exact):

| Panel | Query basis |
|-------|-------------|
| API 5xx ratio | `http_requests_total{status=~"5.."}` / total |
| API p95 latency (global + `by path`) | `http_request_duration_seconds_bucket` via `histogram_quantile` |
| Run outcomes | `runs_total{outcome}` (success/step_budget/time_budget/stuck/error) |
| Queue flow | `rate(jobs_total{state="queued"})` vs `rate(jobs_total{state=~"done\|failed"})` |
| Job failures / dead-letters | `jobs_total{state="failed"}` |
| Probes | `probe_success` (blackbox), `up{job="ghostpanel"}` |

Sentry ([`ops/observability.py`](../ops/observability.py), soft/optional) holds the
exceptions behind 5xx and `outcome="error"` spikes — the complement to the
aggregate alerts.

---

## API availability & latency (SLO: [API availability 99.5%](./slos.md#slo-1--api-availability), [latency p95<1s](./slos.md#slo-2--api-latency))

### `GhostpanelHigh5xxRatioFastBurn` — PAGE
- **Means:** >5% of HTTP responses are 5xx over both 5m and 1h — burning the 0.5%
  availability budget ~14x too fast. Users are seeing errors now.
- **First response:**
  1. `/readyz` — if red, the DB is unreachable → jump to `GhostpanelReadyzDown`.
  2. Correlate with the last deploy (`flyctl releases`, the Deploy action). Recent
     release the likely cause? **Roll back now**
     ([deploy-runbook §Rollback](./deploy-runbook.md#roll-back-the-code-fly-release-rollback)).
  3. Check Sentry for the dominant exception; check `flyctl logs`.
- **Dashboards:** API 5xx ratio, per-route p95 (find the failing route).
- **Escalate:** if not a deploy and not the DB, page the platform owner; declare a
  SEV per [incident-response](./incident-response.md).

### `GhostpanelHigh5xxRatioSlowBurn` — TICKET
- **Means:** 5xx ratio >1% over 30m and 6h (~6x burn). A low, grinding error rate
  that will still exhaust the month.
- **First response:** identify the endpoint/exception from the per-route panel +
  Sentry; fix forward. Not a page unless it accelerates into the fast-burn tier.

### `GhostpanelApiLatencyP95High` — TICKET
- **Means:** global p95 request latency > 1s for 10m.
- **First response:** check the **per-route** p95 panel to localize it. Usual
  causes: slow DB queries (missing index, replica lag, contention), a saturated
  event loop, or an overloaded replica. Check DB CPU/connections; consider
  PgBouncer / adding a replica ([scaling §6](./scaling.md#6-database-scaling)).

### `GhostpanelRouteLatencyP95High` — TICKET (diagnostic)
- **Means:** one route's p95 > 2.5s for 10m. Names the slow endpoint (`$labels.path`)
  before it drags the global SLO across.
- **First response:** profile that route's DB access / downstream calls. Often the
  early warning behind `GhostpanelApiLatencyP95High`.

### `GhostpanelReadyzDown` — PAGE
- **Means:** the blackbox probe of `/readyz` has failed for 3m. The app process is
  up but not ready — **almost always the database is unreachable**. (Requires the
  external blackbox scrape; inactive without it.)
- **First response:**
  1. `curl -i $PROD_BASE_URL/readyz` to confirm.
  2. Check Postgres: provider status page, connection count (exhausted pool looks
     like this), recent migration, network/security-group change.
  3. If a migration just ran and wedged the schema, see
     [deploy-runbook §Rollback the schema](./deploy-runbook.md#roll-back-the-schema-only-if-the-migration-is-at-fault).
- **Escalate:** DB down is a SEV1 candidate — declare early, page platform + DBA.

### `GhostpanelTargetDown` — PAGE
- **Means:** Prometheus can't scrape the app's `/metrics` at all for 3m — the
  replica is down/unreachable (distinct from `/readyz`, which means up-but-not-ready).
- **First response:** `flyctl status` / `flyctl logs`; is the machine crash-looping
  (OOM — Chromium is memory-hungry), failing to boot (bad config/secret), or is
  this a monitoring-network issue? If all replicas are gone it's a SEV1.

---

## Run success (SLO: [run success rate ≥95%](./slos.md#slo-3--run-success-rate-behavioral-runs))

### `GhostpanelRunFailureRateFastBurn` — PAGE
- **Means:** >20% of runs are non-success over 5m and 1h (~4x burn). Note
  "non-success" includes `error`; a behavioral abandonment spike and an infra
  spike both trip this.
- **First response:**
  1. Break down `runs_total{outcome}` — **which** outcome dominates?
     - `error` → infrastructure. Go to `GhostpanelRunInfraErrors` (Holo API down?
       Playwright crashing? worker broken?).
     - `step_budget` / `time_budget` / `stuck` → behavioral or target-site change.
       Did a customer's target site change, or a persona/engine change ship?
  2. Check the **Holo API**: a saturated `HAI_RPM` or a Holo outage makes runs
     time out. Check worker logs for rate-limit / client-build warnings.
  3. Check worker + Playwright health (`--group worker`).
- **Escalate:** infra-driven → SEV2/1 per blast radius; declare an incident.

### `GhostpanelRunFailureRateSlowBurn` — TICKET
- **Means:** >10% non-success over 30m and 6h (~2x burn). Grinding failure.
- **First response:** triage the dominant outcome as above; likely a specific
  persona, target, or a partial Holo degradation. Fix forward.

### `GhostpanelRunInfraErrors` — PAGE
- **Means:** `runs_total{outcome="error"}` rising >0.1/s for 10m — genuine
  infrastructure failure (excluded from survival stats), not user abandonment.
- **First response:**
  1. Sentry for the exception behind the errors.
  2. Holo API reachability + `HAI_API_KEY` validity (a keyless/invalid client makes
     **every** job error at drive time — see `build_holo_client`).
  3. Playwright/Chromium (OOM, missing browser), object storage reachability
     (publish failures are logged, not fatal, but a broader storage outage hurts).
- **Escalate:** if the cause is a dependency (Holo/S3), post to
  [status](./status.md) and follow the sub-processor path in
  [incident-response](./incident-response.md).

---

## Job pipeline (SLO: [enqueue→result](./slos.md#slo-4--enqueue---result-job-pipeline))

### `GhostpanelJobBacklogGrowing` — TICKET
- **Means:** jobs enqueued faster than completed (net > 0.05/s) for 15m — the queue
  is filling.
- **First response:**
  1. Workers alive and claiming? `flyctl logs --group worker`. Scale up
     (`WORKER_CONCURRENCY` / more machines) if simply under-provisioned
     ([scaling §2](./scaling.md#2-workers-are-stateless--scale-them-horizontally)).
  2. Is it **RPM-bound**, not worker-bound? If `HAI_RPM` is saturated, adding
     workers won't help — the fix is a higher tier
     ([scaling §3](./scaling.md#3-the-real-ceiling-model-inference-rpm)). This is
     the most common "backlog" that is actually the model ceiling, not the queue.
  3. Reaper healthy? Stuck `RUNNING` jobs holding slots?
- **Note:** the queue itself does thousands/sec ([load test](../benchmarks/load_test.py));
  a backlog is almost never the queue — it's worker count or RPM.

### `GhostpanelNoJobCompletions` — PAGE
- **Means:** jobs enqueued but **zero** reached done/failed in 10m — the worker
  pool is down or wedged. Sharpest symptom of an enqueue→result breach.
- **First response:**
  1. `flyctl status --app simulation-labs --group worker` — are worker machines
     running at all? Restart / scale up if dead.
  2. `flyctl logs --group worker` — crash loop? OOM? failing to build the Holo
     client (jobs would error, not hang — but a broken boot means no claims)?
  3. DB reachable from workers (they claim via Postgres)?
- **Escalate:** workers-down is SEV2 (runs stall for all tenants); SEV1 if
  prolonged. Declare an incident.

### `GhostpanelJobFailureRateHigh` — TICKET
- **Means:** >10% of terminal jobs are FAILED over 15m — dead-letter pressure.
- **First response:**
  1. Inspect dead-letters: `dead_letters()` in
     [`jobs/reliability.py`](../src/ghostpanel/jobs/reliability.py) lists FAILED
     jobs at `max_attempts`.
  2. Common shape distinct from *run* failures: jobs timing out
     (`DEFAULT_JOB_TIMEOUT_S`), being reaped repeatedly (a target that always
     hangs), or a systematic drive-time error.
  3. Confirm the reaper is running (worker logs: "reaper: recovered N stuck job(s)").

---

## Escalation path (summary)

1. **On-call engineer** — owns first response for every alert above.
2. **Platform / backend owner** — paged when a `page` alert isn't a clean deploy
   rollback within ~15 min, or for any DB/worker-pool-down.
3. **Incident Commander** — for any SEV1/SEV2, per
   [incident-response](./incident-response.md) (the on-call may self-assign IC
   until relieved).
4. **Dependency owners** — Holo (H Company), Stripe, object-storage provider: for
   third-party outages, post to [status](./status.md) and track the vendor's
   incident; there is no local fix.

If a page-severity alert fires and you cannot identify a cause within 15 minutes,
**escalate** — do not sit on it. A rollback is cheap; a prolonged silent outage is
not.
