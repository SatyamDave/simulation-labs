# Security audit — hosted product (Phases 1–4)

Adversarial review of the new surfaces added for the hosted CI product. Evidence is
file:line against branch `product-build-phases-2-5`. Severity: crit / high / med / low.

## Findings

| # | Area | Sev | Location | Issue | Fix |
|---|------|-----|----------|-------|-----|
| 1 | SSRF | high | `server/routers/runs.py` enqueue; `jobs/worker.py:run_job` | The SSRF guard (`cli/safety.assert_url_allowed`) was called **only in the CLI**. The hosted `POST /v2/runs` enqueued any URL and the worker navigated it — a tenant could target `169.254.169.254` (cloud metadata), `localhost`, or RFC-1918 hosts. | **FIXED** — `assert_url_allowed(body.url, allow_private=False)` now runs at enqueue (400 on reject) before a job is created. |
| 2 | AuthZ / IDOR | high | `app.py:199` `app.mount("/artifacts", StaticFiles(...))` | Artifacts (`report.html`, `.webm` videos, `.wav` audio) are served by an **unauthenticated** static mount. Any caller who knows/guesses a `run_id` can read another tenant's run artifacts. Mitigation today: `run_id` is a 48-bit random hex (not enumerable), but it is not access-controlled and IDs leak via report links. | **OPEN (top priority).** Serve artifacts through an authed route `GET /v2/runs/{run_id}/artifacts/{path}` that runs `_run_in_scope` then streams from `ArtifactStorage`; for `<img>/<video>` that can't send a Bearer header, mint short-lived signed URLs (HMAC of `run_id+path+exp` with `SESSION_SECRET`). Until then, treat artifacts as security-through-unguessable-ID and do not enable on truly sensitive tenants. |
| 3 | Session cookie | med | `server/routers/auth.py:_set_cookie` | Cookie sets `httponly` + `samesite=lax` but not `secure`, so it can ride over plain HTTP. The dashboard primarily uses a Bearer token in localStorage, so the cookie is a secondary path, but it should still be `secure` in prod. | Set `secure=True` when the request is https / behind TLS (or gate on a `settings` flag). Low blast radius given Bearer is the main path. |
| 4 | PR-comment content | low | `cli/ci_output.py:pr_comment_md`; `action.yml` github-script step | Run-derived strings (`target_url`, `failure_reason`, captions) are interpolated into Markdown posted as a PR comment. Data originates from the repo's own `sim.yml`/run (self-owned), so injection is low-risk, but a run against an attacker-influenced page could smuggle Markdown. | Escape backticks/pipes/HTML in interpolated run strings before embedding in the comment; the `<!-- simulationlabs-gate -->` marker + github-script `createComment` already treat the body as data, not a template. |
| 5 | Artifact path | low | `storage/local.py`/`s3.py` `put_file/put_dir` | `rel_path` is derived from walking the engine's per-run artifact dir (relative names) under a uuid `run_id`, so traversal isn't reachable from untrusted input today. | Defensively reject `..`/absolute segments in `rel_path` and assert the resolved path stays under the run dir. |

## Verified safe (checked, no action needed)
- **JWT alg confusion** — `auth/tokens.py:34` decodes with `algorithms=["HS256"]` pinned; no `none`/RS/HS confusion.
- **API keys** — stored as SHA-256 of a high-entropy secret; `verify_api_key` uses `hmac.compare_digest` (constant-time); only the prefix is indexed.
- **Run detail / report IDOR** — `runs.py:_run_in_scope` resolves the run, calls `require_project_access(run.project_id)`, and raises **404** (not 403) to hide cross-tenant existence. `/v2/runs`, `/runs/{id}`, `/report`, `/trend`, `/baselines` are all scoped. (Only the static `/artifacts` mount is not — finding #2.)
- **Stripe webhook** — `billing/stripe_client.parse_webhook` verifies the signature via `stripe.Webhook.construct_event` (ValueError on failure); `project_id` comes from session/subscription metadata we set at checkout, not from an attacker-chosen field on an unsigned request.
- **Secret logging** — the access-log middleware logs only `{request_id, method, path, status, duration_ms}`; no Authorization header, API key, HAI key, or token is logged anywhere in `server/`, `jobs/`, `billing/`.
- **Default session secret** — `Settings.session_secret` defaults to an obviously-insecure placeholder; `.env.example` + `docs/deploy.md` flag overriding it in prod. Consider a startup assertion that refuses to boot with the default when a prod flag is set.

## Top 3 to fix before Cohort 01
1. **#2 authed artifacts** — the one real multi-tenant data-exposure gap. Ship the signed-URL/authed-proxy route.
2. **#1 SSRF** — DONE this phase; keep the guard on the enqueue path and add a regression test.
3. **#3 cookie `secure`** + a boot-time check that `SESSION_SECRET` is non-default in production.

Residual/later: #4, #5, per-tenant rate limiting on `/v2/auth/*` (brute force), and adopting Alembic before relying on Postgres (schema drift, see `docs/deploy.md`).
