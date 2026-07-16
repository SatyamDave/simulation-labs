# SOC 2 Type II readiness

**Status: pre-audit self-assessment. Simulation Labs is NOT SOC 2 certified.**

This is an honest, engineering-led readiness matrix mapped to what actually
exists in this repository today, against the AICPA Trust Services Criteria
(TSC) relevant to a hosted SaaS: Security (Common Criteria), Availability, and
Confidentiality. It is written for design partners and early customers who ask
"where are you on SOC 2?" — not as evidence of an audit.

The headline is deliberately unflattering: our **technical control primitives
are strong**, but the **formal compliance program is early**. SOC 2 Type II
requires documented policies, evidence collected *over an audit window*
(typically 3–12 months), independent review, and process controls covering
people — most of which we have **not** started. Do not represent this document
as more than it is.

Legend:

- **Implemented** — the control exists in code/config in this repo and works.
- **Partial** — a control exists but depends on operator configuration, is
  informal, or lacks the policy/evidence a SOC 2 auditor would require.
- **Not-started** — no meaningful control or artifact exists yet.

Scope note: Simulation Labs is a **behavioral / conversion-testing** platform.
Nothing in this document is an accessibility claim; "personas" here are
mechanically-degraded synthetic agents used to measure where conversion flows
break down.

---

## Readiness matrix

### 1. Access control (CC6 — logical access)

| Control | Status | Evidence / gap |
|---------|--------|----------------|
| Authentication (password hashing, session tokens, API keys) | **Implemented** | bcrypt password hashing (`src/ghostpanel/auth/passwords.py`); HS256 session JWTs with pinned algorithm (`src/ghostpanel/auth/tokens.py`); project API keys stored as SHA-256 of a high-entropy secret, verified constant-time (`src/ghostpanel/auth/apikeys.py`). |
| Multi-tenant authorization / isolation | **Implemented** | Every run/report/billing route resolves through `require_project_access` / `_run_in_scope` and returns 404 (not 403) to hide cross-tenant existence (`src/ghostpanel/server/routers/runs.py`). Artifacts are served through the authed `GET /v2/runs/{run_id}/artifacts/{path}` route with short-lived HMAC signed-URL tokens (`src/ghostpanel/server/routers/artifacts.py`, `src/ghostpanel/auth/artifact_tokens.py`) — the old unauthenticated static mount (security-audit finding #2) is closed. |
| Brute-force protection / rate limiting | **Implemented** | Per-IP sliding-window limiter on auth endpoints (`src/ghostpanel/auth/ratelimit.py`). Note the in-process limitation flagged for multi-instance prod (needs a shared store). |
| Internal access provisioning, deprovisioning & periodic access reviews | **Not-started** | No documented process for who has production / cloud-console / database access, no periodic access review, no least-privilege role definitions for staff. This is a people-and-process control an auditor will require. |

### 2. Encryption (CC6.7 — data in transit and at rest)

| Control | Status | Evidence / gap |
|---------|--------|----------------|
| Encryption in transit (TLS) | **Implemented** | Fly terminates TLS with `force_https`; all client↔server and server↔sub-processor traffic is HTTPS/TLS (`docs/deploy.md`, `docs/data-policy.md` §4). |
| Encryption at rest (database + object storage) | **Partial** | Documented as *expected* (SSE-S3/SSE-KMS on the artifact bucket, encrypted DB volume) in `docs/data-policy.md` §4, but it is an **operator responsibility** — not enforced or verified by the application. An auditor would want proof it is enabled on the production accounts. |
| Secrets management | **Partial** | Secrets come only from env / a secrets manager and are never committed; API keys stored only as hashes (`docs/data-policy.md` §4, `.env.example`). Gap: no documented rotation policy or centralized secret store standard; `SESSION_SECRET` strength is an operator checklist item (`docs/deploy.md`), not an enforced boot-time assertion yet. |

### 3. Audit logging (CC7.2 — monitoring / logging)

| Control | Status | Evidence / gap |
|---------|--------|----------------|
| Request / access logging | **Implemented** | Structured JSON access log per request with `X-Request-ID`, method, path, status, duration (`src/ghostpanel/server/middleware.py`). Verified in the security audit to exclude secrets/tokens. |
| Metrics & alerting instrumentation | **Implemented** | Prometheus metrics at `/metrics` (`src/ghostpanel/server/metrics.py`) with SLO-mapped alert rules (`ops/alerts.yml`, `docs/slos.md`). |
| Security audit trail (privileged user actions) + centralized retention / SIEM | **Not-started** | No dedicated, tamper-resistant audit log of security-relevant actions (API-key minting, run deletion, membership changes), no centralized log aggregation/retention, no SIEM. Request logs are operational, not a security audit trail. |

### 4. Change management (CC8.1 — change control)

| Control | Status | Evidence / gap |
|---------|--------|----------------|
| Automated CI on every push / PR | **Implemented** | `.github/workflows/ci.yml` runs ruff, `pytest`, and the web build + tests; frozen contracts guarded by `tests/test_contracts.py`. Coverage gates being added (see `docs/testing.md`). |
| PR-based review workflow | **Partial** | Work lands via branches and PRs (`docs/BRANCHES.md`) and deploys via `.github/workflows/deploy.yml`, but there is no documented change-management *policy*, required-reviewer / branch-protection enforcement evidence, or segregation-of-duties statement. |
| Database schema migrations | **Not-started** | The app uses SQLAlchemy `create_all`, which is dev-only and never alters an existing schema; `docs/deploy.md` and `docs/migrations.md` flag that Alembic must be adopted before relying on Postgres. No migration tooling is in place yet. |

### 5. Availability / BCP (A1 — availability)

| Control | Status | Evidence / gap |
|---------|--------|----------------|
| Health / readiness probes, SLOs & alerting | **Implemented** | `/healthz` + `/readyz`, documented SLOs (`docs/slos.md`), multi-window burn-rate alerts (`ops/alerts.yml`), deploy runbook (`docs/deploy-runbook.md`). |
| Backups | **Implemented** | Logical `pg_dump` backups with a 30-day rolling window and a restore script (`ops/backup.sh`, `ops/restore.sh`, `docs/data-policy.md` §2). |
| Tested DR / restore drills, formal RTO/RPO commitments | **Not-started** | Backups exist but restore drills are not scheduled or evidenced; no committed RTO/RPO, single-region deployment, no documented disaster-recovery plan. An auditor wants proof recovery has actually been exercised. |

### 6. Vendor / sub-processor management (CC9.2)

| Control | Status | Evidence / gap |
|---------|--------|----------------|
| Sub-processor inventory + data-processing terms | **Partial** | A maintained sub-processor list with purpose and data shared exists (`docs/data-policy.md` §5: H Company/Holo, Gradium, Anthropic, Stripe, object storage, optional NVIDIA NemoClaw), and a customer-facing DPA template exists (`docs/dpa-template.md`). Gap: the DPA is a template pending legal review; executed agreements are not tracked in-repo. |
| Formal vendor risk assessment / periodic review | **Not-started** | No documented vendor security assessment, questionnaire process, or scheduled re-review of sub-processors' security posture. |

### 7. Incident response (CC7.3 / CC7.4)

| Control | Status | Evidence / gap |
|---------|--------|----------------|
| Detection & alerting / paging | **Implemented** | Severity-tiered (page / ticket) alerts mapped to SLOs (`ops/alerts.yml`); adversarial security review captured in `docs/security-audit.md`; external responsible-disclosure channel (`docs/security-disclosure.md`). |
| Documented IR plan (severity levels, comms, checklist, postmortem) | **Partial** | An incident-response runbook and on-call runbook are being established alongside this wave (`docs/incident-response.md`, `docs/oncall-runbook.md`). Until they land and are socialized, treat the IR plan as in-progress. |
| Tested IR process + formal on-call rotation | **Not-started** | No evidence of a rehearsed incident (game day / tabletop), no formally staffed on-call rotation, no customer breach-notification runbook exercised. |

### 8. HR / onboarding (CC1.4 — personnel controls)

| Control | Status | Evidence / gap |
|---------|--------|----------------|
| Employee onboarding/offboarding, background checks, security-awareness training, confidentiality agreements | **Not-started** | These are organizational controls outside the codebase and are not yet established. Expected as the team grows; required for a SOC 2 report. |

---

## Summary

| Status | Count |
|--------|-------|
| **Implemented** | 10 |
| **Partial** | 5 |
| **Not-started** | 7 |
| **Total controls assessed** | 22 |

Read this honestly: the **Implemented** items are almost entirely
*technical control primitives* (authn/authz, tenant isolation, TLS, request
logging, CI, backups, alerting) — the things engineers build. The **Partial**
and **Not-started** items (12 of 22) are the *program*: documented policies,
access reviews, at-rest-encryption proof, migration discipline, tested DR,
vendor risk management, a rehearsed incident-response process, and personnel
controls. That is exactly where an early-stage company sits before a real SOC 2
Type II engagement.

### What a real SOC 2 Type II would still require

1. Written policies (information security, access control, change management,
   incident response, vendor management, BCP/DR, HR) — approved and maintained.
2. An audit window (3–12 months) during which control **evidence** is collected
   continuously, not point-in-time.
3. An independent auditor and, typically, a compliance-automation platform
   (Vanta / Drata / Secureframe) to gather evidence.
4. Personnel controls: background checks, onboarding/offboarding, annual
   security training, signed confidentiality agreements.
5. Closing the technical gaps above — notably enforced at-rest encryption
   verification, Alembic migrations, a security audit trail, tested restores,
   and resolving open items in `docs/security-audit.md`.

Owner: Engineering (technical controls) + founders (program & policy). Revisit
this matrix each quarter and before any customer security review.
