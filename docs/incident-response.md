# Incident response

How we declare, run, communicate, and learn from incidents on the Simulation Labs
/ Ghostpanel hosted backend. This is the process layer; the per-alert first
response lives in [`docs/oncall-runbook.md`](./oncall-runbook.md), the
deploy/rollback mechanics in [`docs/deploy-runbook.md`](./deploy-runbook.md), and
what we tell users in [`docs/status.md`](./status.md).

> **Culture:** incidents are **blameless**. We investigate systems and decisions,
> never people. The goal of every incident is a working system and a follow-up that
> stops the same failure recurring silently — not attribution.

---

## Severity levels

Pick the severity from **user impact**, not cause. When unsure, round **up** — you
can always downgrade.

| Sev | Definition | Examples | Response |
|-----|------------|----------|----------|
| **SEV1** | Critical: broad outage or data at risk. Core product unusable for most/all tenants, or a security/data-loss event. | API down (all `/readyz` red), DB unreachable, all workers dead for a sustained period, artifact IDOR / cross-tenant exposure, data loss. | Page immediately, assign IC, all-hands, [status](./status.md) posted, 24×7 until resolved. |
| **SEV2** | Major: significant degradation, workaround may exist. Core flow impaired for many users but not a full outage. | Run success rate spiking (fast-burn page), worker pool wedged (`GhostpanelNoJobCompletions`), elevated 5xx not yet total, billing webhook processing stalled. | Page, assign IC, [status](./status.md) if user-visible, business-priority until mitigated. |
| **SEV3** | Minor: limited or no immediate user impact; a budget is burning. | Slow-burn ticket alerts (latency p95, slow 5xx burn), job backlog growing with healthy workers, a single slow route, dead-letter pressure. | Ticket, triage within the business day, no IC required. |

Mapping from alerts: **`severity: page`** in [`ops/alerts.yml`](../ops/alerts.yml)
is a SEV1/SEV2 candidate; **`severity: ticket`** is typically SEV3. The
[on-call runbook](./oncall-runbook.md) says which is which per alert.

---

## Roles

For SEV1/SEV2, split these across people. On a small team one person may hold two,
but **never** IC + hands-on-keyboard on the same person for long — the IC must stay
above the keyboard.

- **Incident Commander (IC)** — owns the incident, not the fix. Decides severity,
  coordinates, keeps the timeline, makes the rollback/mitigate call, decides when
  it's resolved, and owns the postmortem. The on-call engineer self-assigns IC
  until relieved.
- **Ops / Operations lead** — hands on keyboard: runs diagnostics, executes the
  rollback/mitigation, drives recovery. Follows the [on-call runbook](./oncall-runbook.md).
- **Comms lead** — owns external + internal updates: posts and updates
  [status](./status.md), notifies affected customers, shields Ops/IC from
  question-answering. For SEV3 this folds into the IC.

---

## The first 15 minutes (checklist)

This is the operational sibling of the checklist in
[`docs/deploy-runbook.md`](./deploy-runbook.md#incident-checklist-first-15-minutes)
— that one is command-level; this one is role/process-level.

1. **Declare + timestamp (0–2 min).** State a one-line symptom and a severity.
   Open the incident channel/thread. Assign IC (self-assign if you're on-call).
2. **Assess blast radius (2–5 min).** Staging or prod? How many tenants? Which
   golden signal is red?
   - `curl -i $PROD_BASE_URL/healthz` (liveness) and `/readyz` (DB readiness)
   - `flyctl status` / `flyctl logs` (add `--group worker` — the API checks don't
     cover the worker)
   - Which alert(s) fired → jump to that entry in the [on-call runbook](./oncall-runbook.md).
3. **Communicate (5 min).** Comms lead posts an initial [status](./status.md)
   update for any user-visible SEV1/SEV2 ("investigating"). Set the next-update ETA.
4. **Correlate with change (5–8 min).** Did it start right after a deploy?
   `flyctl releases` + the Deploy action run. Recent migration?
5. **Stop the bleeding (8–12 min).** **Roll back first, diagnose later.** If a
   recent release is the likely cause,
   [roll it back now](./deploy-runbook.md#roll-back-the-code-fly-release-rollback).
   Recovery beats root cause in the moment. Schema only if the migration itself is
   at fault ([schema rollback](./deploy-runbook.md#roll-back-the-schema-only-if-the-migration-is-at-fault)).
6. **Check dependencies (12–15 min).** Postgres (`/readyz`), object storage, and
   the **Holo (HAI) rate limit** — a saturated `HAI_RPM` looks like stuck runs, not
   an outage ([scaling §3](./scaling.md#3-the-real-ceiling-model-inference-rpm)).
   For a third-party outage there is no local fix — post to
   [status](./status.md) and track the vendor.
7. **Verify recovery.** Re-run smoke: `/healthz` + `/readyz` 200, error/latency
   back to baseline, jobs completing again. Update [status](./status.md) to
   "resolved" with the next-steps note.
8. **Hand off to postmortem.** IC opens the postmortem doc while the timeline is
   fresh.

> Data-touching incidents (artifact exposure, deletion, backup/restore) follow
> [`docs/data-policy.md`](./data-policy.md): confirm scope, preserve evidence, and
> honor the breach-notification and deletion obligations there.

---

## Communication plan

- **Internal:** one incident channel/thread per incident. IC narrates decisions;
  Ops narrates actions with timestamps. No side-channels — the thread is the
  timeline.
- **External:** Comms lead owns [`docs/status.md`](./status.md) updates. Cadence:
  initial within ~15 min of a user-visible SEV1/SEV2, then at the stated ETA
  (typically every 30–60 min) until resolved, then a resolution note. Always give a
  **next-update time** even when there's nothing new.
- **Customer-specific:** if a single tenant is affected (their target site, their
  billing), reach them directly rather than the public status.
- **Honest and specific, never speculative on cause** while mitigating. "We are
  investigating elevated errors on the runs API" — not a half-formed root cause.

---

## Postmortem template (blameless)

Write one for **every SEV1 and SEV2** (SEV3 optional, encouraged if it revealed a
gap). Due within **3 business days** of resolution. Copy the block below.

```markdown
# Postmortem — <short title> — <YYYY-MM-DD>

- **Severity:** SEV_
- **Status:** draft | reviewed
- **Authors:** <IC + contributors>
- **Duration:** <first impact> → <resolved> (<total>)
- **User impact:** who, how many, what they experienced, SLO/error-budget spent
  (see docs/slos.md).

## Summary
<2–4 sentences: what broke, blast radius, how it was resolved.>

## Timeline (UTC)
- HH:MM — <event / alert fired / action taken / who>
- HH:MM — ...
- HH:MM — resolved.

## Root cause
<The actual mechanism. Five-whys past the proximate trigger to the systemic cause.
Blameless: describe decisions and system behavior, not individuals.>

## Detection
<Which alert (ops/alerts.yml) caught it, and after how long? Did it page or should
it have? Gap in monitoring?>

## Resolution & recovery
<What actually mitigated it (rollback? scale? dependency recovered?). What we ruled
out.>

## What went well / what went wrong / where we got lucky
- Well: ...
- Wrong: ...
- Lucky: ...  (things that could have been much worse)

## Action items
| Action | Type (prevent / detect / mitigate) | Owner | Due | Tracking |
|--------|-----------------------------------|-------|-----|----------|
| ...    | ...                               | ...   | ... | #issue   |

Each item is concrete and owned. Prefer a test/alert/guardrail so the same failure
cannot recur silently.
```

Every incident must produce **at least one** action item that makes the failure
detectable or impossible next time — a new alert in
[`ops/alerts.yml`](../ops/alerts.yml), a test, a guardrail, or a runbook fix.
