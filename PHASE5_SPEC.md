# Phase 5 spec — QA, security, reliability, launch

> Final phase. Parallel agents, disjoint paths. No `git`. Backend uses the venv;
> web uses npm in `web/`. Build on Phases 1–4 (branch product-build-phases-2-5).

## Goal
Make the product safe to put in front of Cohort 01: continuous integration for the
product itself, observability, a load test at the RPM cap, a real security audit of
the new surfaces, and launch docs (API reference + onboarding runbook).

## Ownership map (no path appears twice)
| Owner | Owns |
|-------|------|
| **P5-A CI + e2e** | `.github/workflows/ci.yml`, `tests/e2e/**` |
| **P5-B observability** | `src/ghostpanel/server/middleware.py`, `tests/server_v2/test_middleware.py` |
| **P5-C security audit** | `docs/security-audit.md` (findings report ONLY — do not edit product code) |
| **P5-D docs + load test** | `docs/api-reference.md`, `docs/onboarding-cohort-01.md`, `docs/index.md`, `benchmarks/load_test.py` |

Orchestrator wires `middleware` into `app.py`, addresses confirmed security findings,
runs the full suite, and commits.

## P5-A — product CI + e2e smoke
- `.github/workflows/ci.yml`: on push + pull_request. Jobs:
  - `python`: setup Python 3.11, `pip install -e ".[dev]"`, `python -m playwright install chromium`,
    `ruff check src tests`, `pytest -q` (the whole suite). Cache pip.
  - `web`: setup Node 20, `npm ci` in web/, `npm run build`, `npm test` (vitest).
  - Keep it green against the current tree — read how tests are invoked (pyproject
    `[tool.pytest.ini_options]`, web `package.json` scripts). Do NOT mark jobs `continue-on-error`.
- `tests/e2e/`: a Playwright-driven smoke that exercises the hosted flow end-to-end WITHOUT
  external APIs — use `FakeHoloClient` + the fixture. A pytest test (reuse the async
  Playwright already a dep) that: builds `create_app(launch_browser=False)` under a live server
  (uvicorn in a thread or httpx ASGITransport), signs up, creates a project + API key, enqueues a
  run against `fixtures/hostile_form.html` (you may drive the worker's `run_job` directly with a
  FakeHoloClient rather than the full queue loop), and asserts a finished RunRow + report. Mark
  slow/browser bits so they can be skipped where chromium is absent. Keep it deterministic.

## P5-B — observability middleware
- `server/middleware.py`: a `RequestContextMiddleware` (Starlette BaseHTTPMiddleware) that assigns
  each request an `X-Request-ID` (accept an inbound one or generate uuid4), binds it + method + path
  + status + duration_ms into a structured (JSON) log line on completion, and sets the header on the
  response. Plus `configure_logging(level)` that installs a JSON formatter on the root logger
  (stdlib logging only — no new deps). Export `add_observability(app)` that adds the middleware and
  a `GET /readyz` route returning `{status:"ok", db:<bool>}` (db check = a cheap `SELECT 1` via
  store.db; degrade to false on error, never raise). Import-safe.
- `tests/server_v2/test_middleware.py`: assert the response carries `X-Request-ID` (and echoes an
  inbound one), `/readyz` returns 200 with the shape, and a log line is emitted (caplog).

## P5-C — security audit (report only)
Adversarially review the NEW surfaces from Phases 1–4 and write findings to
`docs/security-audit.md`. Do NOT edit product code — this is a report the orchestrator acts on.
Cover, with file:line evidence and a severity (crit/high/med/low) + concrete fix each:
- SSRF: `cli/safety.py` (is the guard actually called before every navigation? bypasses? redirects?
  DNS rebinding TOCTOU? does the runner/worker enforce it, or only the CLI?).
- Auth: JWT (alg confusion? secret default in prod?), API keys (hash, timing), session cookie flags,
  `require_project_access` gaps, IDOR on `/v2/runs/{id}` / artifacts (can one tenant read another's
  runs/reports/videos?).
- Stripe webhook: signature verification, replay, project_id spoofing via metadata.
- PR-comment injection: does `ci_output.pr_comment_md` / the Action interpolate untrusted run data
  (URLs, captions) into Markdown/HTML that could break out in a PR comment?
- Secrets: any logged secret (API keys, HAI key, tokens)? the new middleware included.
- Artifact storage: path traversal in `put_dir`/`put_file` rel paths; public S3 URL exposure.
Rank findings; call out the top 3 to fix now vs. later. Be concrete and honest; no hand-waving.

## P5-D — launch docs + load test
- `docs/api-reference.md`: the /v2 API (auth, projects, keys, runs, trend, baselines, billing,
  members) — method, path, auth, request/response shape, error codes. Pull shapes from
  `server/routers/*` so it's accurate.
- `docs/onboarding-cohort-01.md`: the design-partner runbook — from zero to a gated PR
  (install, HAI key, `sim init`, first `sim gate`, add the Action, read the dashboard), plus the
  founding-partner terms framing (ten seats). Behavioral framing (not accessibility).
- `docs/index.md`: a short index linking ci.md, deploy.md, api-reference.md, onboarding, security-audit.
- `benchmarks/load_test.py`: a runnable async script that enqueues N synthetic jobs and drives
  the queue/worker (with a FakeHoloClient, or a stubbed run) to measure claim throughput +
  end-to-end latency under `WORKER_CONCURRENCY`, honestly reporting how the ~5 RPM Holo cap bounds
  real throughput. Prints a small summary table. No network.

## Definition of done
Your files are correct and self-verified (`pytest tests/test_contracts.py` green for backend
agents; `ruff`/`tsc` clean where relevant); only your row touched; no git. P5-C writes findings
only. Report what you did + evidence.
