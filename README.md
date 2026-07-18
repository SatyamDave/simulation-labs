# Simulation Labs — Behavioral Tests for User Flows

**Behavioral tests, like unit tests — but for whether your users can actually finish.**
Your CI blocks a merge when a unit test breaks; Simulation Labs blocks it when your *users*
break. It runs a swarm of computer-use agents ([H Company **Holo**](https://hcompany.ai/holo-models-api),
or Google Gemini via `MODEL_BACKEND=gemini`) against a live flow — checkout, signup, onboarding —
on every deploy, and **fails the build when flow-completion regresses vs the last passing run**.
Each agent's perception and actuation are *mechanically* degraded (coordinate noise for tremor,
tight budgets for impatience, small viewports, blur) so it behaves like a real segment, attempts
the task, and either completes it or **abandons at a specific, reproducible pixel**. You get a
survival curve, an abandonment heatmap over your real page, an **agent-readiness verdict**, video
receipts, and **cloned-voice exit-interviews** ([Gradium](https://gradium.ai)) grounded in each
agent's actual action trace.

Every run also compounds into a cross-site model of where real segments give up, so the next test
is sharper than the last. **Today** you start with a founder-run test of one flow (the on-ramp to
the private beta of the gate); the self-serve gate follows the founding cohort.

Behavioral user research that *does*, not *says*. The internal engine/codebase is named
`ghostpanel` (the Python package); the product/company is **Simulation Labs**.

> Built at H Company's Computer Use Hackathon (SF, Jul 2026). Track 2 — Browser Use.
> Read **[DEMO_PLAYBOOK.md](DEMO_PLAYBOOK.md)** to run it, **[VISION.md](VISION.md)** for the
> pitch, and **[CLAUDE.md](CLAUDE.md)** for the architecture.

---

## Quickstart: the CI gate

Wire the behavioral swarm into CI so every deploy is tested against a real flow and the
build **fails when completion regresses** — a behavioral test suite, like unit tests. Full
guide: **[docs/ci.md](docs/ci.md)**.

```bash
pip install "git+https://github.com/SatyamDave/simulation-labs@main"   # pipx works too
export HAI_API_KEY=hai-...        # your own H Company Holo key — no backend, runs on your key
sim init                          # writes sim.yml + .github/workflows/simulate.yml
sim gate --fail-under last-passing   # exit 1 blocks the merge when users start abandoning
```

`sim baseline` seeds the first green run; after that `sim gate` compares each run against the
last-passing baseline. See **[docs/ci.md](docs/ci.md)** for the `sim.yml` schema, exit codes,
and the GitHub Actions setup (`simulationlabs/gate@v1`).

---

## Why it's different

Every "synthetic user research" tool simulates what users *say* (shallow, people-pleasing).
Ghostpanel simulates what users *do*. Holo is a screenshot-in / action-out model, so we
control the pixels it sees and the clicks it makes — and we degrade them to model real
impairments. **Failure is the product.**

## Architecture (30-second version)

```
web/ (React grid)  ──WS──►  server/ (FastAPI swarm orchestrator)
                                 │  asyncio.gather over personas
                                 ▼
                            runner/ (Playwright)  ──►  engine/ (perturb → Holo → jitter)
                                 │ on finish
                                 ├─►  report/  (survival curve + heatmap)
                                 └─►  voice/   (Gradium exit-interview .wav)
```

All modules talk only through **frozen contracts** in `shared/ghostpanel_contracts/`.
See the file-ownership map and class registry in [CLAUDE.md](CLAUDE.md).

## Repo layout

```
shared/ghostpanel_contracts/  # FROZEN Pydantic models + Protocols (the spine)
src/ghostpanel/{engine,runner,server,voice,report}/   # the five modules
web/                          # React + Vite dashboard
personas/                     # persona JSON configs
fixtures/                     # hostile_form.html + sample screenshot + sample run/events
agents/                       # the five parallel-agent work packages
tests/                        # test_contracts.py (frozen) + per-module tests
```

## Quickstart

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
cp .env.example .env            # add HAI_API_KEY, GRADIUM_API_KEY, ANTHROPIC_API_KEY
pytest tests/test_contracts.py -q

# offline demo target (a deliberately hostile signup flow):
python -m http.server 8137      # → http://localhost:8137/fixtures/hostile_form.html

# run the app (once Agent 3 lands):
python -m ghostpanel.server.main

# benchmarks — swarm quality + runner perf on bundled flows (easy control vs hostile):
python -m ghostpanel.benchmarks                 # offline: runner overhead, no network
python -m ghostpanel.benchmarks --live          # real Holo: completion rate, steps, latency
```

## Sponsors

**H Company** (Holo — the engine) · **Gradium** (voice exit-interviews) ·
**NVIDIA / NemoClaw** (policy-sandboxed swarm) · Accel · AWS.

## Status

**Working end-to-end.** All five modules built (engine, runner, server, voice, report) + the
React frontend. Verified live: real Holo drives real browsers (baseline persona completes the
signup; impaired personas fail differentially at exact pixels), Gradium produces cloned-voice
exit-interviews, and the full pipeline (POST → live WS grid → survival/heatmap report → video +
audio artifacts) runs. Tests: **68 passing** (`pytest -q`). See **[DEMO_PLAYBOOK.md](DEMO_PLAYBOOK.md)**
to run it and for the 90-second demo script. MIT licensed.
