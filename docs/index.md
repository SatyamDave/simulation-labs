# Simulation Labs — docs

Behavioral synthetic users that run your real flows on every deploy and find the
exact pixel where users abandon. We simulate what users **do**, not what they say.

## Start here
- **[Onboarding — Cohort 01](onboarding-cohort-01.md)** — zero to a gated PR (design partners).
- **[CI gate](ci.md)** — the `sim` CLI + `simulationlabs/gate` Action; `sim.yml` schema; exit codes.

## Reference
- **[API reference](api-reference.md)** — the hosted `/v2` API (auth, projects, keys, runs,
  trends, baselines, billing, members).
- **[Deploy / self-host](deploy.md)** — Docker Compose for local, the production operator checklist.
- **[Security audit](security-audit.md)** — findings on the hosted surfaces + what's fixed vs. open.

## The shape of it
```
sim CLI / Action  ──POST /v2/runs──►  API  ──enqueue──►  job queue (Postgres)
                                                              │
                                        worker claims ────────┘
                                        drives the Holo swarm (shared ~5 RPM limiter)
                                        → RunReport persisted, artifacts stored
                                                              │
   dashboard  ◄──/v2 (auth, history, trend, heatmap, baselines, billing)──┘
```
