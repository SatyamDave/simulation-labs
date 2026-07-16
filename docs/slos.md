# Ghostpanel SLOs, error budgets, and alert mapping

This document defines the service-level objectives (SLOs) Ghostpanel commits to,
the error budget each one implies, and how every rule in
[`ops/alerts.yml`](../ops/alerts.yml) protects a specific SLO. It closes the loop
started by the metrics in `src/ghostpanel/server/metrics.py`
(`http_requests_total`, `http_request_duration_seconds`, `runs_total`,
`jobs_total`).

## How to read this

- **SLI** — the measurement (a ratio or quantile derived from `/metrics`).
- **SLO** — the target we hold the SLI to over a 30-day rolling window.
- **Error budget** — `100% - SLO`. When the budget is exhausted, feature work
  pauses in favor of reliability work.
- **Burn rate** — how fast we are consuming the budget relative to spending it
  evenly across the window. Burn rate `1` exhausts the budget exactly at 30
  days; `14.4` exhausts it in ~2 days; `6` in ~5 days.

We alert on **burn rate**, not raw thresholds, using the multi-window method
from the Google SRE workbook: a short window makes the alert responsive, a long
window on the same condition suppresses flapping. Fast burn pages; slow burn
files a ticket.

---

## SLO 1 — API availability

- **SLI:** `1 - (5xx responses / total responses)` from
  `http_requests_total{status,...}`.
- **SLO:** **99.5%** of HTTP requests succeed (non-5xx) over 30 days.
- **Error budget:** **0.5%** of requests may be 5xx (~3.6h of full outage
  equivalent per 30 days).

Rationale: 4xx are client errors and excluded — they don't consume our budget.
The readiness of the process (DB reachable) is part of availability, which is why
the `/readyz` probe also maps here.

### Alerts protecting it
| Alert | Window / condition | Burn | Action |
|-------|--------------------|------|--------|
| `GhostpanelHigh5xxRatioFastBurn` | 5xx ratio > 5% over **5m AND 1h** | ~14.4x | page |
| `GhostpanelHigh5xxRatioSlowBurn` | 5xx ratio > 1% over **30m AND 6h** | ~6x | ticket |
| `GhostpanelReadyzDown` | blackbox `probe_success` of `/readyz` == 0 for 3m | — | page |
| `GhostpanelTargetDown` | `up{job="ghostpanel"}` == 0 for 3m | — | page |

Burn-rate math: with a 0.5% budget, a sustained 5% error rate spends the budget
at `0.05 / 0.005 = 10x`; the two-window guard rounds this to the standard 14.4x
fast-burn tier and only fires when both the 5m and 1h windows agree, so a brief
blip does not page. The 1% / 6x slow-burn tier catches a low, grinding error rate
that would still exhaust the month.

---

## SLO 2 — API latency

- **SLI:** p95 of `http_request_duration_seconds` (from the histogram
  `_bucket` series via `histogram_quantile`).
- **SLO:** **p95 < 1s** for API requests (measured over 5m windows, held 99% of
  the time across 30 days).
- **Error budget:** up to 1% of 5m windows may exceed the p95 target.

### Alerts protecting it
| Alert | Condition | Action |
|-------|-----------|--------|
| `GhostpanelApiLatencyP95High` | global p95 > 1s for 10m | ticket |
| `GhostpanelRouteLatencyP95High` | any route p95 > 2.5s for 10m | ticket |

The per-route alert exists so a single slow endpoint is named before it drags the
global p95 across the line — it is diagnostic, keyed on the same histogram with a
`by (le, path)` aggregation.

---

## SLO 3 — Run success rate (behavioral runs)

- **SLI:** `success runs / total runs` from `runs_total{outcome}`. Only
  `outcome="success"` counts as good.
- **SLO:** **>= 95%** of runs complete successfully over 30 days.
- **Error budget:** **5%** non-success.

Definitional note: per the contracts, `outcome="error"` is *infrastructure*
failure (excluded from survival/abandonment statistics). For the **SLO** we
still count non-success = `outcome != "success"` because a spike in any
non-success outcome is operationally interesting. To keep infra failures from
hiding behind behavioral abandonment, `GhostpanelRunInfraErrors` isolates
`outcome="error"` on its own page-level alert.

### Alerts protecting it
| Alert | Window / condition | Burn | Action |
|-------|--------------------|------|--------|
| `GhostpanelRunFailureRateFastBurn` | non-success > 20% over **5m AND 1h** | ~4x | page |
| `GhostpanelRunFailureRateSlowBurn` | non-success > 10% over **30m AND 6h** | ~2x | ticket |
| `GhostpanelRunInfraErrors` | `outcome="error"` rate > 0.1/s for 10m | — | page |

Burn-rate math: against a 5% budget, a sustained 20% failure rate burns at
`0.20 / 0.05 = 4x`; 10% burns at `2x`. Run volume is spikier than HTTP traffic
(a swarm launches many personas at once), so the fast-burn threshold is set
higher (20%) and the `for:` is a touch longer to avoid paging on a single small
batch that happened to abandon.

---

## SLO 4 — Enqueue -> result (job pipeline)

- **SLI (latency):** p95 time from job `queued` to terminal (`done`/`failed`).
  Today this is measured indirectly via queue throughput; a direct
  `job_duration_seconds` histogram is a future addition.
- **SLI (throughput):** completion rate keeps pace with enqueue rate, from
  `jobs_total{state}` (a counter of state transitions).
- **SLO:** **p95 enqueue->result < 5 min** under nominal load, and the queue does
  not grow unboundedly (net enqueue-minus-completion rate ~0 over any 15m
  window).
- **Error budget:** 1% of 5m windows may exceed the latency target; sustained
  backlog growth is a budget-burning event.

Because `jobs_total` records transitions (not a live gauge), backlog is inferred
by differencing rates: `rate(queued) - rate(done|failed)`. A persistent positive
difference means the queue is filling.

### Alerts protecting it
| Alert | Condition | Action |
|-------|-----------|--------|
| `GhostpanelJobBacklogGrowing` | `rate(queued) - rate(done+failed) > 0.05/s` for 15m | ticket |
| `GhostpanelNoJobCompletions` | enqueues > 0 but zero completions for 10m | page |
| `GhostpanelJobFailureRateHigh` | FAILED / terminal > 10% for 15m | ticket |

`GhostpanelNoJobCompletions` is the "workers are down/wedged" page — the sharpest
symptom of an enqueue->result breach. `GhostpanelJobFailureRateHigh` watches
dead-letter pressure and pairs with the W1-A reliability reaper
(`reap_stuck_jobs` / `dead_letters`).

---

## Alert -> SLO map (summary)

| Alert | Metric(s) keyed on | SLO |
|-------|--------------------|-----|
| `GhostpanelHigh5xxRatioFastBurn` | `http_requests_total{status}` | API availability |
| `GhostpanelHigh5xxRatioSlowBurn` | `http_requests_total{status}` | API availability |
| `GhostpanelReadyzDown` | `probe_success` (blackbox, external) | API availability |
| `GhostpanelTargetDown` | `up` (Prometheus, external) | API availability |
| `GhostpanelApiLatencyP95High` | `http_request_duration_seconds_bucket` | API latency |
| `GhostpanelRouteLatencyP95High` | `http_request_duration_seconds_bucket` | API latency |
| `GhostpanelRunFailureRateFastBurn` | `runs_total{outcome}` | Run success rate |
| `GhostpanelRunFailureRateSlowBurn` | `runs_total{outcome}` | Run success rate |
| `GhostpanelRunInfraErrors` | `runs_total{outcome="error"}` | Run success rate |
| `GhostpanelJobBacklogGrowing` | `jobs_total{state}` | Enqueue -> result |
| `GhostpanelNoJobCompletions` | `jobs_total{state}` | Enqueue -> result |
| `GhostpanelJobFailureRateHigh` | `jobs_total{state}` | Enqueue -> result |

All metric names above match `src/ghostpanel/server/metrics.py` exactly. The
blackbox/`up` probes require an external Prometheus scrape config (documented
inline in `ops/alerts.yml`); every other rule works against the app's own
`/metrics` endpoint with no extra infrastructure.

---

## Error-budget policy (operating rule)

- **Budget healthy (< 50% consumed):** ship freely.
- **Budget > 50% consumed:** review reliability risk in each change.
- **Budget exhausted:** freeze non-reliability changes until the SLI recovers and
  the rolling window heals.
- **Any page-severity alert:** follow the incident steps in
  `docs/deploy-runbook.md` (rollback, migration, escalation).

Sentry (wired via `ops/observability.py`, soft/optional) captures the exceptions
behind 5xx and `outcome="error"` spikes; it complements — never replaces — these
aggregate SLO alerts.
