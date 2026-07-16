# Responsible disclosure policy

Simulation Labs runs swarms of behavioral synthetic personas against a
customer's live website to measure where a real conversion flow (sign-up,
checkout, cancel) breaks down. Because the product drives real web
applications and stores run recordings, we take the security of the platform
and our customers' data seriously. If you have found a vulnerability, we want
to hear about it.

This document is the human-readable policy referenced by
[`/.well-known/security.txt`](../landing-page/.well-known/security.txt)
(RFC 9116).

> **Placeholder note.** The contact address below (`security@simulationlabs.example`)
> is a placeholder. Replace it with the production security inbox before go-live.

---

## How to report

Email **security@simulationlabs.example** with:

- a description of the issue and the surface it affects (API, dashboard, CI
  gate / GitHub Action, artifact storage, a sub-processor path);
- the steps or a proof-of-concept needed to reproduce it;
- the impact you believe it has (e.g. cross-tenant data access, auth bypass,
  SSRF);
- your name / handle if you would like to be credited.

If the report contains sensitive details, ask us for a PGP key in your first
message and we will provide one (no key is published yet — see *Limitations*).

Please do **not** open a public GitHub issue for a security report, and do not
disclose the issue publicly until we have confirmed a fix or agreed a
disclosure date with you.

---

## Response SLA

These are the targets we hold ourselves to, measured in business days:

| Stage | Target |
|-------|--------|
| Acknowledge receipt | within **2 business days** |
| Initial triage + severity assessment | within **5 business days** |
| Status updates while we work | at least every **7 days** |
| Fix or mitigation for high/critical issues | targeted within **30 days** of triage |

We will keep you informed through remediation and let you know when a fix ships.

---

## Scope

**In scope**

- The hosted API (`/v2/*` endpoints: auth, projects, API keys, runs, reports,
  billing, artifacts).
- The dashboard web app.
- The CI gate / GitHub Action integration (`action.yml`, the CLI auth path).
- Artifact storage and delivery (the authed
  `GET /v2/runs/{run_id}/artifacts/{path}` route and its signed-URL tokens).
- Authentication and multi-tenant isolation (session JWTs, project API keys,
  per-project scoping).
- The public landing / docs site.

Vulnerability classes we especially want to hear about: cross-tenant data
access (IDOR), authentication or authorization bypass, SSRF via a run target
URL, injection, secret exposure, and any way to read another tenant's run
artifacts (screenshots / video / audio).

**Out of scope**

- Findings that require a compromised host, rooted device, or physical access.
- Denial of service, volumetric / load testing, or automated scanning that
  degrades the service for others. (Note: our own free tier shares a single
  rate-limited model client — do not attempt to exhaust it.)
- Social engineering, phishing, or physical attacks against Simulation Labs
  staff, customers, or offices.
- Missing security headers, cookie flags, or TLS configuration **without a
  demonstrated, concrete impact**.
- Reports generated solely by an automated tool with no validated exploit.
- Vulnerabilities in third-party sub-processors (H Company / Holo, Gradium,
  Anthropic, Stripe, our object-storage provider) — report those to the vendor;
  we will help coordinate if a Simulation Labs surface is involved.
- Best-practice or informational findings already documented as known
  limitations in [`docs/security-audit.md`](./security-audit.md) and
  [`docs/deploy.md`](./deploy.md) (e.g. adopting Alembic before relying on
  Postgres, the operator's obligation to set a strong `SESSION_SECRET`).
- Content of the target website a customer chooses to point a swarm at — that
  is the customer's own property, not ours.

---

## Safe harbor

We will not pursue or support legal action against researchers who, in good
faith:

- make a genuine effort to avoid privacy violations, data destruction, and
  service interruption;
- access, store, and use only the **minimum** data necessary to demonstrate a
  vulnerability, and do not access, modify, or exfiltrate data belonging to
  other tenants beyond what is needed to prove the issue;
- give us a reasonable opportunity to remediate before any public disclosure;
- do not use the vulnerability beyond proof-of-concept, and permanently delete
  any tenant data they incidentally accessed once the report is filed;
- stay within the in-scope surfaces above and respect the out-of-scope list.

If you are unsure whether an action is authorized, ask us first at the contact
address. Good-faith research conducted consistent with this policy is
considered authorized, and we will work with you rather than against you. This
safe harbor covers only Simulation Labs systems — it does not authorize
testing against our sub-processors or against customer-owned target sites.

---

## Limitations (what we are honest about today)

- **No bug bounty yet.** We do not currently offer monetary rewards. We deeply
  appreciate responsible reports and will credit researchers (with your
  permission) in an acknowledgements list. We expect to introduce a paid
  program as the platform matures.
- **No published PGP key yet.** Request one in your first message and we will
  share a key for sensitive follow-ups.
- **Early-stage program.** SLAs are targets, not contractual guarantees. We are
  a small team; we will communicate honestly if something takes longer.

---

## Acknowledgements

Researchers who report valid issues will be listed here (opt-in). Thank you for
helping keep Simulation Labs and its customers safe.
