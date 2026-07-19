# Contributing to Simulation Labs

Thanks for being here. Simulation Labs is behavioral user research that *does*, not *says* —
a swarm of computer-use agents that attempt your real flows and report where users abandon.
The most useful contributions push on exactly that.

## Get set up

```bash
git clone https://github.com/SatyamDave/simulation-labs
cd simulation-labs
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
pytest -q          # 416 tests should pass
```

Then prove the whole thing works end to end on your own key:

```bash
export GEMINI_API_KEY=...      # or HAI_API_KEY — any model key auto-detects
sim try
```

## Where help is most valuable

- **New behavioral segments** — a `personas/*.json` that mechanically models a real slice of
  traffic (a new degradation, a new budget). Ground it in a real-world condition, not a
  medical label — we model *how people behave*, not who they are.
- **New model backends** — any OpenAI-compatible vision endpoint. See
  `src/ghostpanel/engine/models/` for the backend registry and add-a-backend pattern.
- **Real flows that break the gate** — point `sim gate` at a live flow that surfaces an
  interesting abandonment, and share the report. These become our best test fixtures.
- **Docs & DX** — anything that makes the first `sim try` smoother for a stranger.

## Ground rules

- **Everything ships working.** No half-wired features, no commands that error, no docs that
  claim something the code doesn't do. If it's not ready, keep it on a branch.
- Cross-module boundaries speak in typed contract models, never bare dicts — see
  [`docs/CONTRACTS.md`](docs/CONTRACTS.md).
- Add tests under `tests/<yourmodule>/`; keep the suite green.
- Type-hint public functions; async in the engine/runner/server.

## Reporting bugs & ideas

Open a [GitHub issue](https://github.com/SatyamDave/simulation-labs/issues). For behavioral
false-positives/negatives, include the flow URL (or a repro fixture), the persona, and the
report `.json` if you can.

## Talk to us

Want to run this on your funnel, partner, or just compare notes? Open an issue or email the
founder at **satyam@agentmade.ai**.
