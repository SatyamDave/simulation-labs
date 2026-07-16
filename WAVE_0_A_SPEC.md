# Wave 0 (launch blockers) + Wave A (inference at scale) — build spec

> Parallel agents, disjoint paths, frozen interfaces. No `git`. Backend uses the venv;
> web uses npm in `web/`. Contracts (`tests/test_contracts.py`) stay green. Build on
> branch product-build-phases-2-5 (phases 1–5 complete). See PRODUCTION_PLAN.md for why.

## Frozen foundations (READ-ONLY — orchestrator authored)
- `auth/artifact_tokens.py` — `sign_artifact(run_id, rel_path, secret, ttl_s=)` /
  `verify_artifact(run_id, rel_path, token, secret)` (HMAC, expiring).
- `storage/base.py` — the `ArtifactStorage` Protocol now also has
  `async read(run_id, rel_path) -> bytes|None` (traversal-safe) and
  `presigned_url(run_id, rel_path, expires_s=) -> str|None` (None ⇒ caller streams).
- `auth/deps.py` (`require_project_access`, `optional_user`, `current_project`),
  `store/*`, `server/config.Settings`.

## Ownership map (no path appears twice)
| Owner | Owns | Notes |
|-------|------|-------|
| **SEC-A** artifact auth | `server/routers/artifacts.py`, `storage/local.py`, `storage/s3.py`, `tests/server_v2/test_artifacts.py` | orchestrator removes the open /artifacts mount + includes this router + updates FE links |
| **SEC-B** auth hardening | `auth/ratelimit.py`, `server/routers/account.py`, `tests/auth/test_hardening.py` | cookie/secret changes to existing files are done by the ORCH (call them out in your report) |
| **INF-A** model registry | `engine/models/__init__.py`, `engine/models/registry.py`, `engine/models/echo.py`, `tests/engine/test_registry.py` | Holo stays the default; add a 2nd trivial backend to prove the seam |
| **INF-B** queue fairness | `jobs/scheduler.py`, `tests/jobs/test_scheduler.py` | per-tenant fair-share claim on top of the existing JobQueue; do NOT edit queue.py |
| **PLAT** migrations | `alembic.ini`, `migrations/**`, `docs/migrations.md` | initial migration from the current SQLModel metadata |
| **SRE** observability | `server/metrics.py`, `tests/server_v2/test_metrics.py` | Prometheus-style /metrics; counters/histograms for runs, jobs, http |

## SEC-A — authed artifacts (closes the HIGH IDOR)
- `storage/local.py`: implement `read` — resolve `run_id/rel_path` under root, **reject
  traversal** (`..`, absolute, symlink escape) by returning None; return bytes or None.
  `presigned_url` → None (local streams).
- `storage/s3.py`: `read` → download bytes (asyncio.to_thread); `presigned_url` →
  boto3 `generate_presigned_url("get_object", ...)` with expiry.
- `server/routers/artifacts.py`: `GET /v2/runs/{run_id}/artifacts/{path:path}`.
  Authorize the caller for the run's project via **either** a session cookie/bearer or
  api-key (reuse the run-scoping pattern from `routers/runs.py` `_run_in_scope`), **or**
  a valid `?token=` (`verify_artifact` with `settings.session_secret`). On success: if
  `storage.presigned_url(...)` returns a URL → `RedirectResponse(url)`, else stream
  `storage.read(...)` bytes with a guessed content-type (404 if None). 404 (not 403) on
  cross-tenant to hide existence. Add a helper `signed_artifact_path(run_id, rel, secret)`
  returning `/v2/runs/{id}/artifacts/{rel}?token=...` for the orchestrator/FE.
- tests: same-project member streams; cross-tenant → 404; valid token works, expired/bad
  token → 401/403; traversal (`../../etc/passwd`) → 404.

## SEC-B — auth hardening
- `auth/ratelimit.py`: a small in-process sliding-window limiter
  `RateLimiter(max, per_seconds)` + an async FastAPI dependency factory
  `limit_by_ip(bucket, max, per_seconds)` keyed on client IP (X-Forwarded-For aware).
  (In-process is fine for now; note Redis for multi-instance in your report.)
- `server/routers/account.py`: `POST /v2/auth/request-password-reset {email}` (always
  200, no user enumeration; returns a reset token in dev when email isn't configured),
  `POST /v2/auth/reset-password {token,new_password}`, `POST /v2/auth/verify-email {token}`,
  `POST /v2/auth/request-verify` — token via `auth/tokens` JWT with a purpose claim (add a
  `issue_purpose_token`/`decode_purpose_token` ONLY if needed — otherwise reuse with a
  distinct short TTL and a `typ` claim you validate). Store nothing new (stateless tokens).
- tests: reset flow round-trips; wrong/expired token rejected; no email enumeration
  (same response for known/unknown email); ratelimiter blocks after N.
- REPORT (do not edit): tell the orchestrator to (a) set cookie `secure=True` behind TLS
  in `routers/auth.py:_set_cookie`, (b) add a boot check refusing the default
  `SESSION_SECRET` in prod, (c) attach `limit_by_ip` to `/v2/auth/login|signup`.

## INF-A — pluggable model backend (respects the frozen HoloClient contract)
- `engine/models/registry.py`: `build_model(name, settings) -> HoloClient` mapping
  `"holo"` → `LiveHoloClient(...)` (from settings) and `"echo"` → the trivial backend;
  `available()` lists names; unknown → ValueError. Read `MODEL_BACKEND` (add nothing to
  Settings — read `os.environ.get("MODEL_BACKEND","holo")` inside the registry, or accept a
  param). The worker/app will call `build_model` instead of constructing LiveHoloClient
  directly (orchestrator wires that).
- `engine/models/echo.py`: `EchoModelClient` — a deterministic `HoloClient` (satisfies the
  runtime-checkable Protocol) that returns simple scripted actions; proves a non-Holo
  backend plugs in. (Model-agnostic; good for offline tests/CI.)
- tests: `build_model("holo",...)` is a HoloClient; `build_model("echo",...)` is a
  HoloClient and `isinstance(x, HoloClient)`; unknown → ValueError.

## INF-B — per-tenant fair scheduling
- `jobs/scheduler.py`: `FairClaim(queue)` wrapping `JobQueue` — when many tenants have
  queued jobs, round-robin across `project_id` so one tenant can't starve others (the
  shared model RPM is the scarce resource). `claim(worker_id)` picks the oldest job of the
  least-recently-served project. Pure Python over the queue's read + the guarded update;
  do NOT modify queue.py. Deterministic + tested with a temp DB (3 tenants, assert fairness).

## PLAT — Alembic
- `alembic.ini` + `migrations/` (env.py wired to `SQLModel.metadata` + async engine from
  `store.db`); one initial revision that creates the current schema. `docs/migrations.md`:
  how to autogenerate + upgrade, and that prod must use this instead of create_all.
- Verify `alembic upgrade head` builds the schema on a temp sqlite equal to create_all.

## SRE — metrics
- `server/metrics.py`: a tiny Prometheus text exposition (no new deps — hand-roll the
  format, or use stdlib) with counters (`runs_total{outcome}`, `jobs_total{state}`,
  `http_requests_total{path,status}`) + a request-duration histogram, and
  `add_metrics(app)` registering `GET /metrics` + a middleware feeding http counters.
  Import-safe. tests: `/metrics` returns text; counters increment after a request.

## DoD
Frozen signatures respected; `pytest tests/test_contracts.py` green; only your row; no git.
Backend agents run their own tests + report real output. Orchestrator integrates
(remove open mount, wire routers/model registry/metrics, FE artifact links), runs the full
suite + web build, addresses findings, commits.
