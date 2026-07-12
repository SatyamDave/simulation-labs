# Ghostpanel / Simulation Labs — Documentation

Complete technical documentation for the Ghostpanel codebase and every branch in the repository. Start here.

> **Ghostpanel** is a swarm of **behavioral synthetic users**. It points Holo-powered personas — each with **mechanically degraded** perception and actuation (blur, tremor, colour-vision loss, small viewports, impatience) — at a live website with a real goal, and records whether each persona completes the task or **abandons at a specific pixel**. Output: a survival curve, an abandonment heatmap, video receipts, and voice exit-interviews.

---

## Read in this order

1. **[ARCHITECTURE.md](ARCHITECTURE.md)** — the whole system: end-to-end data flow, the two golden rules (true-pixel coordinates + frozen contracts), external integrations, config & artifacts.
2. **[CONTRACTS.md](CONTRACTS.md)** — the frozen `shared/ghostpanel_contracts/` reference: every model, enum, the `RunEvent` WebSocket union, and the six Protocols.
3. **[BRANCHES.md](BRANCHES.md)** — full branch topology & lineage, the commit graph, and which branches are on origin.

---

## Module references

The system is built by **five parallel agents on five branches** that merge with zero conflicts by coding against the contracts. Each module is documented in depth:

| Module | Path | Owner | Doc |
|---|---|---|---|
| **Engine** | `src/ghostpanel/engine/` | Agent 1 | **[modules/ENGINE.md](modules/ENGINE.md)** — Holo client (live + fake), 8 personas, perturbations, prompts, coordinate denormalization. |
| **Runner** | `src/ghostpanel/runner/` | Agent 2 | **[modules/RUNNER.md](modules/RUNNER.md)** — Playwright session loop, execute/detect/thumbnail, the simulated-clock patience fix. |
| **Server** | `src/ghostpanel/server/` + `app.py` | Agent 3 | **[modules/SERVER.md](modules/SERVER.md)** — FastAPI API, WebSocket hub, swarm manager, composition root. |
| **Web** | `web/` | Agent 4 | **[modules/WEB.md](modules/WEB.md)** — React live grid, report view, offline demo, the v3 design system. |
| **Voice + Report** | `src/ghostpanel/voice/` + `report/` | Agent 5 | **[modules/VOICE_REPORT.md](modules/VOICE_REPORT.md)** — survival/heatmap report, HTML leave-behind, Gradium exit interviews. |

---

## Branch-specific documentation

| Branch | Doc |
|---|---|
| **`repeated-bathroom`** (the "god-tier round") | **[branches/REPEATED_BATHROOM.md](branches/REPEATED_BATHROOM.md)** — NemoClaw policy cage, stats/WCAG insights, leaderboard, before/after compare, verified success. |

---

## The two lineages at a glance

- **`main` / `debug` line** — the integrated five-agent system + UI reskins (v2 → v3) + the sim-clock patience fix. `origin/main` (= `debug` = `416e488`) is the tip; local `main` (= `design-system` = `17eb398`) is one commit behind it.
- **`repeated-bathroom` line** — a divergent sibling that forked *before* the five-agent merge and grew a larger, different feature set. On origin as `origin/repeated-bathroom`.

See **[BRANCHES.md](BRANCHES.md)** for the full graph.

---

## Repository top-level (for orientation)

- `src/ghostpanel/` — the five Python modules (engine, runner, server, voice, report) + `app.py` composition root.
- `web/` — the React/Vite frontend.
- `shared/ghostpanel_contracts/` — the **frozen** cross-module contracts.
- `personas/*.json` — the 8 persona configs.
- `fixtures/` — offline demo data (`run.json`, `events.jsonl`), test targets (`hostile_form.html`, and on `repeated-bathroom` `payment_form.html` / `hostile_form_fixed.html`), `sample_screenshot.png`.
- `tests/` — per-module test suites + `tests/test_contracts.py` (must stay green).
- Root docs: `CLAUDE.md` (build guide), `VISION.md`, `ROADMAP.md`, `DEMO_PLAYBOOK.md`, `README.md`.

---

## Running it locally

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
cp .env.example .env            # fill in HAI_API_KEY, GRADIUM_API_KEY, ANTHROPIC_API_KEY
pytest tests/test_contracts.py -q

# backend
ghostpanel                      # uvicorn factory → http://127.0.0.1:8000

# frontend (separate terminal)
cd web && npm install && npm run dev      # http://localhost:5173
```

The frontend also ships a **zero-backend offline demo** (fixtures-driven) reachable from the launch screen — useful when no API keys are available.
