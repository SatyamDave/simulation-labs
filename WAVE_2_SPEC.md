# Wave 2 — scale & polish (final wave) — build spec

> Parallel agents, disjoint paths. No `git`. Backend uses the venv; web uses npm in `web/`.
> Contracts stay green; web tsc stays clean. Build on branch product-build-phases-2-5
> (phases 1–5 + Waves 0/A/1). See PRODUCTION_PLAN.md Wave 2.

## Ownership map (no path appears twice)
| Owner | Owns |
|-------|------|
| **W2-A** frontend polish | `web/src/main.tsx`, `web/vite.config.ts`, `web/src/dashboard/components/ErrorBoundary.tsx`, `web/src/dashboard/components/Fallback.tsx` |
| **W2-B** coverage gates | `.github/workflows/ci.yml`, `web/vitest.config.ts`, `docs/testing.md` |
| **W2-C** trust & compliance | `landing-page/.well-known/security.txt`, `docs/security-disclosure.md`, `docs/soc2-readiness.md`, `docs/dpa-template.md` |
| **W2-D** scale & ops docs | `docs/scaling.md`, `docs/oncall-runbook.md`, `docs/incident-response.md`, `docs/status.md` |

Orchestrator handles pyproject coverage dep + any wiring, runs the full suite + web
build, commits.

## W2-A — frontend polish (perf + a11y + resilience)
- `web/src/main.tsx`: code-split the dashboard — convert the dashboard page imports
  (Runs, RunDetail, Flows, Members, Billing, Settings, and Login/Signup) to `React.lazy`
  + wrap the routed `<Outlet>`/element tree in `<Suspense fallback={<Fallback/>}>`. Keep
  the demo `App` eager (it's the "/" landing). Wrap the dashboard subtree in `<ErrorBoundary>`.
  Goal: the initial bundle no longer ships the whole dashboard; each page is a chunk.
- `web/vite.config.ts`: add `build.rollupOptions.output.manualChunks` splitting vendor
  (react/react-dom/react-router-dom, framer-motion) from app code. Keep existing plugins/server.
- `ErrorBoundary.tsx`: a class component catching render errors → a friendly recover card
  (reload / back to runs), theme-aware, no crash-to-white-screen.
- `Fallback.tsx`: an accessible route-loading fallback (role=status, sr-only label) reused as the Suspense fallback.
- a11y/perf: ensure the new bits have focus-visible states, `prefers-reduced-motion` respected
  where you add motion, and no layout shift. Do NOT rewrite sibling pages; keep changes scoped.
- VERIFY: `npx tsc --noEmit` clean; `npm run build` succeeds and now emits MULTIPLE JS chunks
  (report the chunk list + that the main entry shrank vs the ~433KB single bundle); `npm test` green.

## W2-B — coverage gates + testing docs
- Install `pytest-cov` (`uv pip install --python .venv/bin/python pytest-cov`; tell the
  orchestrator to add `pytest-cov>=5` to the dev extra). Add a `[tool.coverage.run]`/`report`
  section RECOMMENDATION in your report (orchestrator edits pyproject).
- `.github/workflows/ci.yml`: extend the existing jobs — python job runs `pytest --cov=ghostpanel
  --cov-report=term-missing --cov-fail-under=70` (pick a floor at/below current coverage so it
  passes today — MEASURE it first and set the floor just under); web job runs `npm test` with
  coverage (`vitest run --coverage`). Keep the existing steps. Valid YAML.
- `web/vitest.config.ts`: add `test.coverage` (provider v8, reporters text+json, a sane threshold
  that passes today — measure first).
- `docs/testing.md`: how to run backend + web tests + coverage locally, the philosophy (contracts
  frozen, offline determinism, adversarial verify), and the coverage floors + why.
- VERIFY: run `pytest --cov=ghostpanel --cov-report=term -q` (paste the total %), set the CI floor
  just under it; `cd web && npx vitest run --coverage` (paste total). YAML valid. Report the floors chosen.

## W2-C — trust & compliance artifacts
- `landing-page/.well-known/security.txt` (RFC 9116: Contact, Expires, Policy, Preferred-Languages).
- `docs/security-disclosure.md`: responsible-disclosure policy (scope, safe harbor, how to report,
  SLA, no-bounty-yet framing honest).
- `docs/soc2-readiness.md`: an HONEST SOC 2 Type II readiness checklist mapped to what EXISTS in
  this repo (access control = auth/tenancy, encryption = TLS+at-rest expectations, audit logging =
  request-id logs, change mgmt = CI/CD + PRs, BCP = backups) vs. GAPS (no formal policies, no
  vendor risk mgmt, no employee onboarding controls). Do not overclaim — mark each control
  Implemented / Partial / Not-started with a pointer to the file or the gap.
- `docs/dpa-template.md`: a data-processing-addendum TEMPLATE (sub-processors from data-policy.md,
  data categories, security measures, deletion) clearly labeled a template for legal review.
- Framing: behavioral/conversion testing, NOT accessibility. VERIFY: security.txt parses (has
  Contact + Expires); links resolve. Report the control status table summary.

## W2-D — scale & ops docs
- `docs/scaling.md`: how the system scales — workers are stateless (scale horizontally; the DB
  queue + FairClaim already coordinate; the shared model RPM is the real ceiling — quantify),
  when to move from the DB queue to a broker (Redis/NATS) and how, artifact CDN via S3
  public_base_url, DB read-replicas, and the honest bottleneck analysis (inference, not the queue).
- `docs/oncall-runbook.md`: alerts (from ops/alerts.yml) → response steps, dashboards, escalation.
- `docs/incident-response.md`: severity levels, comms, the 15-min checklist, postmortem template.
- `docs/status.md`: a simple public status/uptime communication plan + the components users care
  about (API, dashboard, run workers, model inference). (A doc, not a live service.)
- Cross-reference ops/alerts.yml + docs/slos.md + docs/deploy-runbook.md. VERIFY: links resolve;
  the scaling bottleneck section is honest about the RPM ceiling. Report the doc outline.

## DoD
Only your row; no git. Backend: contracts green. Web: tsc clean + build + tests green.
Report real verification output.
