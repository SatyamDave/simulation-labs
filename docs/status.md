# Status & uptime communication plan

How Simulation Labs communicates service health to customers. **This is a plan, not
a live status service** — it defines the components we track, how we post during an
incident, and how we announce maintenance, so that when a status page is stood up
(e.g. a hosted Statuspage/Instatus, or a static page) it has a spec to follow.

It is the customer-facing end of the operational chain:
[`docs/oncall-runbook.md`](./oncall-runbook.md) (per-alert response) →
[`docs/incident-response.md`](./incident-response.md) (how we run an incident) →
this doc (what customers see) → [`docs/slos.md`](./slos.md) (the reliability targets
we hold ourselves to).

---

## Components customers track

The status page reports these four components independently, because they fail
independently and a customer's mental model maps to them directly:

| Component | What it means to a customer | Backing signal(s) |
|-----------|-----------------------------|-------------------|
| **API** | The `/v2` API and CI gate (`sim` CLI, GitHub Action) can create runs, fetch results, auth. | `/healthz`, `/readyz`, `GhostpanelHigh5xxRatio*`, `GhostpanelTargetDown`, `GhostpanelReadyzDown` |
| **Dashboard** | The web app loads and shows runs, trends, heatmaps, billing. | Same `app` process as the API; API 5xx/latency alerts. |
| **Run workers** | Enqueued swarms actually execute and produce reports. | `GhostpanelNoJobCompletions`, `GhostpanelJobBacklogGrowing`, `GhostpanelJobFailureRateHigh` |
| **Model inference** | The Holo vision model that drives personas is available and within rate. | `GhostpanelRunInfraErrors`, `GhostpanelRunFailureRate*`, worker Holo-client logs |

Notes that keep this honest:

- **API and Dashboard share one process group** (`app` in [`fly.toml`](../fly.toml))
  but are listed separately because customers experience them separately; if the
  cause is shared, post the same incident against both.
- **Run workers is a distinct component.** A healthy API with dead workers means
  "you can submit runs but they won't execute" — a real, separately-communicated
  state (the API health checks do **not** cover the worker).
- **Model inference is a dependency, largely upstream.** Degradation here is often
  the shared Holo rate limit (`HAI_RPM`) or an H Company outage — we can report and
  route around it (per [scaling §3](./scaling.md#3-the-real-ceiling-model-inference-rpm)),
  but the fix may be a vendor's. We say so plainly.

### Component states

`Operational` · `Degraded performance` · `Partial outage` · `Major outage` ·
`Under maintenance`. These map to incident severity in
[`docs/incident-response.md`](./incident-response.md): a SEV1 → Major outage on the
affected component(s); SEV2 → Partial outage / Degraded; SEV3 usually stays
Operational (a burning budget with no user-visible impact is not posted).

---

## How incidents are posted

Owned by the **Comms lead** during an incident
([incident-response §Roles](./incident-response.md#roles)). Cadence and content:

1. **Investigating** — within ~15 min of a user-visible SEV1/SEV2. Name the
   affected component(s) and symptom, no speculative cause. State the next-update
   time.
2. **Identified** — once the cause/mitigation is known ("a recent deploy is being
   rolled back", "upstream model provider degraded").
3. **Monitoring** — mitigation applied, watching for recovery.
4. **Resolved** — service back to baseline; one-line cause + that a postmortem will
   follow for SEV1/SEV2.

Rules:

- **Always give a next-update time**, even with nothing new ("next update by
  16:30 UTC"). Silence is worse than "still working on it".
- **Honest and specific, never blame a customer or speculate on root cause** while
  mitigating. Match the tone in [incident-response](./incident-response.md).
- **Single tenant affected?** Don't post publicly — contact that customer directly
  (their target site changed, their billing, their project). Public status is for
  shared impact.
- **Dependency outages** (Holo / Stripe / object storage — the sub-processors in
  [`docs/data-policy.md`](./data-policy.md#5-sub-processors)) are posted against the
  component they affect ("Model inference — degraded: upstream provider incident"),
  with a link to the vendor's status where useful.
- After a SEV1/SEV2, the resolution note links to (or promises) the blameless
  postmortem ([template](./incident-response.md#postmortem-template-blameless)).

---

## Maintenance windows

- **Planned maintenance** is announced on the status page **≥48h ahead** for any
  window with expected user impact, with start/end in UTC and the components
  affected.
- **Prefer zero-downtime.** The deploy pipeline is a rolling deploy with
  migrate-before-deploy and forward-compatible migrations
  ([deploy-runbook](./deploy-runbook.md), [migrations](./migrations.md)), so most
  releases need **no** maintenance window and are not posted.
- **A window is only needed** for changes that can't be done rolling — e.g. a
  destructive migration that isn't forward-compatible, or a provider-side DB
  upgrade. Set the component to **Under maintenance** for the window and back to
  **Operational** after verifying smoke.
- **Emergency maintenance** (a fix that can't wait for a 48h notice) is posted as
  an incident, not a planned window, with the reason stated.

---

## Uptime reporting

- Publish **uptime per component** against the [SLOs](./slos.md) — API availability
  targets **99.5%** over 30 days; run success targets **≥95%**. Report the rolling
  30-day number so customers see the same window we budget against.
- Uptime is derived from the same probes the alerts use (`probe_success` for
  `/readyz`, `up` for the scrape target — see
  [`ops/alerts.yml`](../ops/alerts.yml)); the status page should not invent a
  second source of truth.
- Do **not** count `4xx` (client errors) or behavioral run abandonment
  (`step_budget`/`time_budget`/`stuck`) against uptime — only infra failure
  (`5xx`, `outcome="error"`, workers down). This matches the SLI definitions in
  [`docs/slos.md`](./slos.md) and keeps the number meaningful.

---

## When the status page itself is down

Host the status page **off** the primary infrastructure (a third-party status
provider, or a static page on separate hosting/CDN) so it survives a full backend
outage — a status page that shares fate with the API is useless exactly when it's
needed. Until a hosted page exists, the fallback channel is direct customer
notification (email to affected tenants) per the comms plan above.
