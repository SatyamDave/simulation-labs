# Wave 1 — production hardening — build spec

> Parallel agents, disjoint paths, frozen interfaces. No `git`. Backend uses the venv.
> Contracts stay green. Build on branch product-build-phases-2-5 (phases 1–5 + Wave 0/A).
> See PRODUCTION_PLAN.md Wave 1.

## Context you can rely on (READ-ONLY)
- Queue: `jobs/queue.py` (`JobQueue`: enqueue/claim/mark_done/mark_failed; JobRow has
  `state, attempts, max_attempts, locked_by, locked_at, started_at, finished_at`).
- Scheduler: `jobs/scheduler.py` (`FairClaim`). Worker: `jobs/worker.py` (`run_job`, `_worker_loop`).
- Metrics: `server/metrics.py` — `inc_run(outcome)`, `inc_job(state)` ready to call.
- Store/db: `store/db.session_scope`, `store/models.py` (JobRow, JobState, RunRow, RunState).
- Billing: `billing/{stripe_client,usage,entitlements}.py`.
- Deploy: `Dockerfile`, `docker-compose.yml`, `fly.toml`, `.github/workflows/{ci,pages}.yml`.

## Ownership map (no path appears twice)
| Owner | Owns |
|-------|------|
| **W1-A** job reliability | `jobs/reliability.py`, `tests/jobs/test_reliability.py` |
| **W1-B** CI/CD deploy | `.github/workflows/deploy.yml`, `docs/deploy-runbook.md` |
| **W1-C** data lifecycle | `ops/backup.sh`, `ops/restore.sh`, `ops/retention.py`, `docs/data-policy.md` |
| **W1-D** billing correctness | `billing/reconcile.py`, `tests/billing/test_reconcile.py`, `docs/billing-ops.md` |
| **W1-E** SLOs + alerting | `ops/alerts.yml`, `ops/observability.py`, `docs/slos.md` |

Orchestrator wires reliability + metrics counters into the worker loop, adds Sentry
init if W1-E provides it, and commits. `ops/` is a new top-level dir (create it).

## W1-A — job reliability
`jobs/reliability.py` (pure functions/helpers over `session_scope` + models; do NOT edit
queue.py):
- `async reap_stuck_jobs(*, lease_seconds=900) -> int`: find JobRow in RUNNING with
  `locked_at` older than lease_seconds and re-QUEUE them (clear lock/started) if
  `attempts < max_attempts`, else mark FAILED (dead-letter). Return count reaped.
- `async run_with_timeout(coro, *, timeout_s) -> ...`: `asyncio.wait_for` wrapper raising a
  clear `JobTimeout` on expiry (the worker wraps run_job with this).
- `DEFAULT_JOB_TIMEOUT_S`, `DEFAULT_LEASE_S` constants.
- `async dead_letters(project_id=None, limit=50) -> list[JobRow]`: list FAILED jobs at
  max_attempts (for an ops view).
Tests (temp DB): a RUNNING job with an old locked_at is requeued; one past max_attempts is
FAILED; a fresh RUNNING job is untouched; run_with_timeout raises JobTimeout on a slow coro.
Report to orchestrator: wire `reap_stuck_jobs` on an interval in the worker loop + wrap
run_job in run_with_timeout.

## W1-B — CI/CD staged deploy
`.github/workflows/deploy.yml`: on push to main (+ workflow_dispatch). Jobs:
`build` (docker build), `migrate` (run `alembic upgrade head` against the target DB
from a secret — gate deploy on it), `deploy-staging` (deploy the image; e.g. fly deploy
to a staging app), `smoke` (curl /readyz + /healthz on staging), `deploy-prod` (needs a
GitHub Environment approval + green smoke), with a documented rollback (redeploy previous
image / `fly releases`). Use placeholders + comments for the real secrets/targets (FLY_API_TOKEN,
DATABASE_URL). Valid YAML (`python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))"`).
`docs/deploy-runbook.md`: deploy, rollback, migration, incident steps.

## W1-C — data lifecycle
- `ops/backup.sh` (pg_dump to a timestamped file / S3; env-driven; `set -euo pipefail`),
  `ops/restore.sh` (guarded restore with a confirm prompt).
- `ops/retention.py`: an async script that deletes run artifacts + RunRows older than N days
  (configurable; dry-run default) via session_scope + the storage abstraction; prints what it
  would delete. No network beyond storage.
- `docs/data-policy.md`: what data we store (incl. screenshots/video of customer flows =
  sensitive), retention windows, deletion on request (GDPR/CCPA), sub-processors.
Verify: `bash -n ops/*.sh` (syntax), `python ops/retention.py --dry-run --days 30` runs on a
temp DB (guard so it never touches ghostpanel.db).

## W1-D — billing correctness
- `billing/reconcile.py`: `async reconcile_project(project_id, settings) -> dict` that fetches
  the Stripe subscription (via stripe_client — add a thin `get_subscription_status(secret, sub_id)`
  ONLY in your file if needed, or monkeypatchable) and corrects the project tier via
  `usage.set_project_billing` if drifted; `async reconcile_all(settings)`. Idempotent.
  Document webhook replay/idempotency (Stripe event ids) + proration + dunning in `docs/billing-ops.md`.
- tests (stripe monkeypatched, temp DB): a project marked team but Stripe says canceled →
  reconcile downgrades to free; in-sync → no change; idempotent on re-run.

## W1-E — SLOs + alerting
- `ops/alerts.yml`: Prometheus alerting rules over the /metrics we expose (high http 5xx rate,
  run failure-rate SLO burn, job queue backlog, /readyz down). Real PromQL against
  `http_requests_total`, `runs_total`, `jobs_total`, `http_request_duration_seconds`.
- `ops/observability.py`: `init_sentry(dsn)` (no-op when dsn empty / sentry not installed —
  import guarded so it never hard-deps), returning whether it initialized; a helper the app can
  call. Do NOT add sentry to deps — soft dependency.
- `docs/slos.md`: the SLOs (run success rate, enqueue→result p95, availability), error budgets,
  and how the alerts map to them.

## DoD
Frozen signatures; `pytest tests/test_contracts.py` green; only your row; no git. Backend
agents run their own tests + report. Shell/YAML agents validate syntax. Orchestrator wires
reliability + metrics + sentry, runs the full suite, commits.
