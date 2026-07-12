# 👻 Ghostpanel

**Synthetic users that _do_, not say.** A swarm of [H Company **Holo**](https://hcompany.ai/holo-models-api)
computer-use agents that attempt real tasks on your website — each one a persona whose
perception and actuation are *mechanically* degraded (blur for low vision, coordinate noise
for tremor, tight budgets for impatience) — and either finish or **abandon at a specific
pixel**. You get a survival curve, an abandonment heatmap, video receipts, and **voice
exit-interviews** ([Gradium](https://gradium.ai)) where each dead persona explains why it quit.

> Built at H Company's Computer Use Hackathon (SF, Jul 2026). Track 2 — Browser Use.
> Read **[VISION.md](VISION.md)** for the pitch and **[CLAUDE.md](CLAUDE.md)** for the architecture.

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
```

## Sponsors

**H Company** (Holo — the engine) · **Gradium** (voice exit-interviews) ·
**NVIDIA / NemoClaw** (policy-sandboxed swarm) · Accel · AWS.

## Status

Scaffold + frozen contracts on `main`. Five modules built in parallel per
[ROADMAP.md](ROADMAP.md). MIT licensed.
