# Simulation Labs — docs

Behavioral synthetic users that run your real flows on every deploy and find the
exact pixel where users abandon. We simulate what users **do**, not what they say.

## Start here
- **[Quickstart & CI gate](ci.md)** — the `sim` CLI + `simulationlabs/gate` Action; `sim.yml` schema; exit codes.
- **[Self-hosting](SELF_HOSTING.md)** — run the whole thing on your own machine, on your own model key.

## Reference
- **[Architecture](ARCHITECTURE.md)** — how a run flows from CLI to swarm to report.
- **[Contracts](CONTRACTS.md)** — the typed models every module speaks in.
- **[API reference](api-reference.md)** — the `/v2` API (auth, projects, keys, runs, trends, baselines).
- **[Testing](testing.md)** — how the suite is structured and how to run it.

## Trust & data
- **[Data policy](data-policy.md)** — what is sent to your model provider and what never leaves your machine.
- **[Security disclosure](security-disclosure.md)** — how to report a vulnerability.
- **[DPA template](dpa-template.md)** — a starting-point data-processing agreement.

## The shape of it
```
sim CLI / Action  ──►  swarm of degraded browser agents  ──►  each attempts your flow
                                                                    │
                                       completes ✓ or abandons ✗ at a specific pixel
                                                                    │
                              RunReport: completion rate · survival curve · abandonment heatmap
```
