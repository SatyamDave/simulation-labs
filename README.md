<div align="center">

# Simulation Labs

### A behavioral CI gate — real computer-use agents attempt your signup, checkout, and onboarding on every deploy, and block the merge when your users start abandoning.

Unit tests prove your code runs. **They say nothing about whether a human can finish the flow.**
Simulation Labs sends a swarm of browser agents — some steady, some rushed, some fumbling a
small control on a phone — at a live page. Each one either completes the task or **abandons at a
specific, reproducible pixel**. You get a completion rate, an abandonment heatmap over your real
page, and a non-zero exit code when it regresses.

[![MIT License](https://img.shields.io/badge/license-MIT-black.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-black.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-416%20passing-black.svg)](tests/)
[![Backends](https://img.shields.io/badge/backend-Gemini%20·%20Holo%20·%20self--host-black.svg)](#bring-any-key)

**[▶ Watch the 2-min demo](https://simulationlabs.dev/demo/)** · **[See a real report](https://simulationlabs.dev/sample-report/)** · **[Why this exists](VISION.md)**

</div>

---

## 60-second quickstart

One command. No account, no config, no signup. Bring any model key you already have.

```bash
pip install "git+https://github.com/SatyamDave/simulation-labs@main"
playwright install chromium

export GEMINI_API_KEY=...        # or HAI_API_KEY, or point at a self-hosted model — any key works
sim try
```

`sim try` spins up a real signup page, sends five behavioral agents at it, and shows you the
result live:

```
  Fluent          success          ✓
  AI Agent        success          ✓
  Mobile-thumb    success          ✓
  Rushed          stuck            ✗
  Misclick-prone  step_budget      ✗   ← abandoned at the consent checkbox

  Completion rate: 60%  (3/5)

  ✓ it works. That was real browser agents attempting a real signup flow.
    open the full report:  .sim-try/…/report.html
```

The steady agents finish. The imprecise one fumbles a small checkbox and gives up — exactly
where a slice of your real traffic does. **That gap is the thing nobody else measures.**

Don't have a key? Get a [free Gemini key](https://aistudio.google.com/apikey) — the free tier
runs `sim try` end to end.

---

## Point it at your own flow

```bash
sim gate \
  --url https://your-app.com/signup \
  --task "create an account with email and password"
```

Exit code `0` if completion holds, `1` if it regressed. That's the whole contract — it drops
straight into any CI:

```yaml
# .github/workflows/simulate.yml
- run: pip install "git+https://github.com/SatyamDave/simulation-labs@main"
- run: playwright install chromium
- run: sim gate --url ${{ env.PREVIEW_URL }} --task "create an account"
  env:
    GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

`sim init` writes the workflow and a `sim.yml` for you. `sim baseline` seeds the first green
run; after that every `sim gate` compares against the last passing one and tells you **which
kind** of failure it caught:

- **`FUNCTIONAL_FAIL`** — even an undegraded agent can't finish. The flow is broken. Block the merge.
- **`BEHAVIORAL_REGRESSION`** — it still works for a steady user, but a segment that used to
  complete now abandons. A UX regression a unit test would wave through. Block it anyway.

---

## Bring any key

There is no Simulation Labs backend to sign up for. The agent runs on **your** inference. Set
any one of these and the CLI auto-detects it:

| Backend | Env var | Notes |
|---|---|---|
| **Google Gemini** | `GEMINI_API_KEY` | Free tier runs `sim try` end to end |
| **H Company Holo** | `HAI_API_KEY` | Purpose-built computer-use model |
| **Self-hosted** | `MODEL_BACKEND=selfhost` + `MODEL_BASE_URL` | Any OpenAI-compatible vision endpoint |
| **Echo (offline)** | `MODEL_BACKEND=echo` | Deterministic, no network — for tests/CI dry-runs |

Drop a key in `.env` and it loads automatically. Nothing leaves your machine except the
screenshots you send to the model provider you chose.

---

## How it works

The agent is screenshot-in, action-out: it sees a picture of the page and returns a click or
keystroke. Because we own that loop, we can **mechanically** shape what it perceives and how
precisely it acts — reproducing behavioral segments instead of guessing at them.

```
   screenshot ──►  perturb (per segment)  ──►  model  ──►  action  ──►  jitter coords  ──►  click
                   blur / downscale / crop            (Gemini/Holo)      tremor noise
```

| Segment | What we change | Models the user who… |
|---|---|---|
| **Fluent** | nothing (control) | finishes cleanly — your baseline |
| **AI Agent** | nothing (control) | is an autonomous agent filling your form |
| **Rushed** | tight step + time budget | bounces if it takes too long |
| **Mobile-thumb** | small viewport | is on a phone with a fat-finger tap target |
| **Misclick-prone** | coordinate noise on every click | fumbles small controls and gives up |

The controls set the ceiling; the degraded agents show you how far below it your real traffic
sits, and **where** — down to the pixel — they walk away.

**What you get per run:** a completion rate, a survival curve, an abandonment heatmap painted
over your real screenshot, video receipts of each session, and grounded exit-interview
transcripts explaining the abandonment. See a full one: **[live sample report](https://simulationlabs.dev/sample-report/)**.

---

## Architecture

```
web/ (live grid)  ──WS──►  server/ (async swarm orchestrator)
                              │  one asyncio task per agent
                              ▼
                         runner/ (Playwright)  ──►  engine/ (perturb → model → jitter)
                              │ on finish
                              ├─►  report/  (completion rate + survival + heatmap)
                              └─►  voice/   (grounded exit-interview)
```

Everything crossing a module boundary is a typed contract, not a dict. `sim try`, `sim gate`,
`sim baseline`, and `sim init` are the four commands you need. 416 tests, MIT licensed.

## Contributing

Issues and PRs welcome — especially new behavioral segments, new model backends, and real-world
flows that break the gate in interesting ways. `pip install -e ".[dev]" && pytest` to get started.

## License

MIT. Use it, fork it, ship it.

---

<div align="center">
<sub>Behavioral user research that <b>does</b>, not <b>says</b>. · <a href="https://simulationlabs.dev">simulationlabs.dev</a></sub>
</div>
