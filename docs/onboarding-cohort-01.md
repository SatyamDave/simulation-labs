# Cohort 01 — design-partner onboarding

Welcome. Simulation Labs runs a swarm of **behavioral synthetic users** against your
real flows on every deploy and tells you the exact pixel where users abandon — we
simulate what users *do*, not what they say. This is the zero-to-gated-PR runbook.

## 0. What you'll have at the end
A PR check that runs your real flow (say, checkout) with a swarm of ICP-calibrated
behavioral agents and **fails the build when completion drops** — behavioral tests,
like unit tests — plus a dashboard showing the completion trend across deploys and
the abandonment heatmap for each run.

## 1. Install the CLI (5 min)
```bash
pip install "git+https://github.com/SatyamDave/simulation-labs@main"   # PyPI: coming
python -m playwright install chromium
export HAI_API_KEY=hk-...        # your H Company Holo key (hub.hcompany.ai)
```

## 2. Author your first flow
```bash
sim init                         # writes sim.yml + .github/workflows/simulate.yml
```
Edit `sim.yml` — one flow to start:
```yaml
flows:
  - name: checkout
    url: https://staging.example.com/checkout
    task: "Add the item to the cart and complete checkout"
    fail_under: last-passing      # block the merge if completion drops vs the last green run
icp:
  personas: auto                  # the full behavioral roster; or list specific segments
```

## 3. Run it locally, set a baseline
```bash
sim run                          # runs the swarm, writes .sim/report.{json,html}
sim baseline                     # save this run as "last passing"
sim gate --fail-under last-passing   # exits non-zero if the next run regresses
```
Open `.sim/report.html` to see the survival curve, heatmap, and video receipts.
(Free/OSS tier is ~5 Holo RPM, so swarms are small and paced — depth over breadth.)

## 4. Wire it into CI
1. Add repo secret **`HAI_API_KEY`**.
2. Commit the generated `.github/workflows/simulate.yml` (uses `simulationlabs/gate@v1`
   with `flow`, `icp`, `fail-under: last-passing`).
3. Open a PR — the gate runs, comments the heatmap + completion delta, and fails the
   check if users start abandoning. See [docs/ci.md](ci.md).

## 5. The dashboard
Sign in at your instance (`/login`), create a project + an **API key** (Settings),
and point `--remote`/the Action at it to see: run history, the completion-**trend
over deploys** line (did this deploy make it worse?), per-run heatmaps, and baselines.
Invite teammates on the Members page (Team tier).

## Founding-partner terms
Cohort 01 is **ten partners, first come**. Partners get founding-partner terms,
a direct line to the team, and real influence on the roadmap. When the tenth seat is
taken the cohort closes and the next one is months out. If you're reading this, you're in.

Questions → the shared channel. Docs hub: [docs/index.md](index.md).
