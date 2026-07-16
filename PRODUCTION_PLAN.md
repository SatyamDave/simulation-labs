# Simulation Labs — production-grade plan

Status: **proposal, awaiting go.** Nothing here is built yet. This is the path from
"code-complete prototype" (branch `product-build-phases-2-5`: phases 1–5, all tests
green) to a product safe to put real tenants, real URLs, and real money in front of.

## The bar
Production-grade ≠ more features. It means: **secure by default, doesn't lose data,
degrades gracefully, observable when it breaks, and trustworthy with a stranger's
staging URLs + payment details.** Every item below is judged against that, not "does
it demo."

## Decided constraints (from review)
- **Inference: paid/partner Holo tier is coming.** So we design for a *configurable,
  high RPM* and make the model backend **pluggable** (Holo is one of N computer-use
  models) — no single-vendor lock, and the swarm scales past the 5-RPM free-tier toy.
  This is Workstream A and gates the product's core promise (per-deploy swarms).
- Everything else assumes A lands.

## Owners (execution model)
Role-based leads; most workstreams run as a parallel agent fan-out against a frozen
spec (as phases 2–5 did). **Security- and money-touching work the orchestrator does
directly, then a human reviews.** Human gates are called out explicitly — they are not
optional and not automatable.

| Tag | Lead |
|-----|------|
| INF | Inference/platform |
| SEC | Security (orchestrator-authored + human review) |
| PLAT | Backend platform |
| SRE | Reliability/observability |
| FE | Frontend |
| BILL | Billing |
| QA | Test/load/chaos |
| DOC | Docs/support |

Estimate scale: **S** ≈ one agent, ½ day · **M** ≈ small fan-out, 1–2 days · **L** ≈
multi-agent + human review, 3–5 days. Calendar assumes review gates, not just codegen.

---

## Wave 0 — Launch blockers (nothing real ships until these close)

| # | Workstream | Deliverable | Owner | Est | Exit criteria |
|---|-----------|-------------|-------|-----|---------------|
| 0.1 | SEC | **Close artifact IDOR.** Replace the unauthenticated `/artifacts` mount with an authed proxy `GET /v2/runs/{id}/artifacts/{path}` (runs `_run_in_scope`) + short-lived HMAC-signed URLs for `<img>/<video>`. Dashboard + report links use signed URLs. | orch + human | M | No path serves another tenant's artifacts; regression test proves cross-tenant 403/404. |
| 0.2 | SEC | **Auth hardening.** Cookie `secure`; refuse default `SESSION_SECRET` at boot in prod; per-IP rate-limit `/v2/auth/*`; email verification + password reset; API-key rotation. | orch + human | L | Auth review checklist passes; brute-force throttled; no default secret in prod. |
| 0.3 | SEC | **Independent security review** of auth, billing, webhook, SSRF, artifact access. This is AI-written code guarding money — a human (or dedicated adversarial pass) signs off. | human | M | Sign-off recorded; criticals/highs closed. |
| 0.4 | INF | **Verify a real Holo run** end-to-end (paid key, live API) through enqueue→worker→report→artifacts. Today every test uses FakeHoloClient. | INF | M | One real paid run green in staging; coord-space + rate-limit confirmed live. |
| 0.5 | PLAT | **Alembic migrations** replacing `create_all`; provisioned managed Postgres; migration runs in the deploy pipeline. | PLAT | M | `alembic upgrade head` is the only way schema changes; create_all removed from prod path. |
| 0.6 | PLAT | **Deploy to staging** (the fly.toml/compose we have) with real secrets, TLS, a domain. | SRE | M | Staging URL live; `/readyz` green; a real signup+gated-PR works there. |

**Wave 0 exit:** a first design partner could use it on staging without us exposing
their data or losing their runs.

---

## Wave A — Inference at scale (the core promise) — parallel with Wave 0

| # | Deliverable | Owner | Est |
|---|-------------|-------|-----|
| A.1 | **Pluggable model interface** — abstract perception/action behind a `VisionActionModel` protocol; Holo (`LiveHoloClient`) becomes one backend; add a second (e.g. another computer-use model) to prove the seam. | INF | L |
| A.2 | **Rate limiter + queue redesign for high/configurable RPM** — per-tenant + global limits, fair scheduling across the swarm, backpressure; workers scale horizontally off the shared budget. | INF/PLAT | L |
| A.3 | **Capacity model + per-tier concurrency** — map RPM → personas → wall-clock; enforce per-tier swarm size; surface honest ETAs in the UI. | INF | M |
| A.4 | **Cost accounting** — track model calls per run/tenant; feed usage metering + billing. | BILL/INF | M |

**Wave A exit:** a real per-deploy swarm (not 4 serialized personas) completes in
minutes at the paid tier, and the model vendor is swappable.

---

## Wave 1 — Production hardening

| # | Workstream | Deliverable | Owner | Est |
|---|-----------|-------------|-------|-----|
| 1.1 | SRE | **Observability**: OTel metrics + traces, dashboards, alerting on SLOs (run success rate, enqueue→result p95, error rate), `/metrics`, Sentry. Not just JSON logs. | SRE | L |
| 1.2 | SRE | **SLOs + error budgets** defined and monitored; runbook per alert. | SRE | M |
| 1.3 | PLAT | **Job reliability**: idempotent enqueue, timeouts + dead-letter queue, stuck-run reaping, worker crash recovery, graceful shutdown, DB pool tuning. | PLAT | L |
| 1.4 | SRE | **CI/CD**: staged deploys (preview→staging→prod), migration gating, post-deploy smoke, one-command rollback. | SRE | M |
| 1.5 | PLAT | **Data lifecycle**: automated Postgres + artifact backups, restore drills, retention + PII policy for run artifacts (screenshots of customer flows are sensitive — legal weight). | PLAT | L |
| 1.6 | BILL | **Billing correctness**: webhook idempotency + replay protection, proration, seat sync, failed-payment dunning, reconciliation job. | BILL | L |
| 1.7 | QA | **Real e2e + load + chaos** against live inference limits; kill workers/DB mid-run and prove recovery. | QA | L |

**Wave 1 exit:** on-call can operate it; a bad deploy rolls back; a crash loses no run;
billing reconciles.

---

## Wave 2 — Scale & polish

| # | Workstream | Deliverable | Owner | Est |
|---|-----------|-------------|-------|-----|
| 2.1 | PLAT | Horizontal workers; a real broker (Redis/NATS) if the DB queue saturates; artifact CDN; multi-region-ready storage. | PLAT | L |
| 2.2 | FE | **Frontend to the bar**: audited loading/empty/error states, real a11y pass, perf budget + code-splitting (bundle is ~430KB today), design QA, keyboard/focus. | FE | L |
| 2.3 | DOC | Docs site, public status page, support runbooks, on-call rotation. | DOC/SRE | M |
| 2.4 | SEC | **Compliance path**: SOC 2 readiness, DPA, `security.txt`, responsible-disclosure, pen test. | SEC/human | L |
| 2.5 | QA | Coverage gates in CI (backend + web), mutation testing on the money/auth paths. | QA | M |

**Wave 2 exit:** it scales with demand, looks and feels first-party, and can pass a
customer's security questionnaire.

---

## Cross-cutting definition of done (applies to every task)
- Tested (unit + integration; e2e for user-facing; contracts stay green).
- Observable (emits metrics/logs with request IDs; failures are visible).
- Reversible (migration down-path or feature flag; safe rollback).
- Documented (API reference + runbook updated).
- Reviewed (human review on anything touching auth, billing, or tenant data).

## Sequencing
```
Wave 0  ─┐  (blockers; ship to staging)
Wave A  ─┘  (parallel; the core promise) ──► Wave 1 (harden) ──► Wave 2 (scale/polish)
                                              │
                    human security sign-off ──┘ (gate before prod / real money)
```
Wave 0 + A run concurrently. Wave 1 needs both. Wave 2 is post-first-revenue polish.

## Risks (honest)
- **Inference economics.** Paid Holo cost per run × swarm size may make per-commit
  gating expensive; A.3/A.4 exist to price and cap it. If unit economics don't work,
  reposition to nightly/depth (the fallback we discussed).
- **AI-authored surface area.** ~15k lines across phases 1–5 written by agents; the
  security review (0.3) and billing correctness (1.6) are where that risk concentrates.
- **Single model vendor** until A.1 lands.
- **Legal/PII.** Storing customer-flow screenshots/video is regulated data; 1.5 + 2.4
  are not optional if you take EU/enterprise customers.

## Explicitly operator (human) responsibilities — not automatable
Provisioning prod infra, real Holo/Stripe/domain secrets, the security sign-off,
the SOC 2 process, and the pricing/positioning call on inference economics.

---

*On go, I'll execute Wave 0 + Wave A as parallel agent fan-outs against frozen specs
(as before), do 0.1/0.2 myself for the security-sensitive parts, and stop at each human
gate for your review.*
