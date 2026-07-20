<div align="center">

# Simulation Labs

### A behavioral CI gate — real computer-use agents attempt your signup, checkout, and onboarding on every deploy, and block the merge when the flow breaks for your users.

</div>

```
Simulation Labs — behavioral gate demo
▷ No key set — replaying real recorded runs.  (set GEMINI_API_KEY to run it live)
→ genuine recorded runs of the bundled signup flow, 2026-07-19 — no model is called; every number below is from those runs.

① A working signup flow — five behavioral segments attempt it:

  PERSONA         OUTCOME  STEPS
  ------------------------------
  Fluent          success      4  ✓
  AI Agent        success      4  ✓
  Rushed          success      4  ✓
  Mobile-thumb    success      4  ✓
  Misclick-prone  success      5  ✓

Completion rate: 100%  (5/5 personas completed)

  gate PASS ✓  — completion 100%. This is your green baseline.

② The same flow on a regressed build (a deploy broke the submit):

  PERSONA         OUTCOME      STEPS
  ----------------------------------
  Fluent          stuck            5  ✗  ← gave up at (638, 566)
  AI Agent        stuck            5  ✗  ← gave up at (638, 566)
  Rushed          stuck            7  ✗  ← gave up at (638, 568)
  Mobile-thumb    step_budget      6  ✗  ← gave up at (6, 491)
  Misclick-prone  step_budget      5  ✗  ← gave up at (475, 478)

Completion rate: 0%  (0/5 personas completed)

  gate FAIL ✗  — completion 0% (was 100%). The build broke the flow — the merge is blocked. (exit 1)

That's the whole contract: green when your users can finish, red — with the exact failures — when they can't.

▷ recorded (working run: gemini; regressed-build run: holo, 2026-07-19) · set GEMINI_API_KEY to run this live, or point it at your own flow:
  sim gate --url https://your-app.com/signup --task "create an account"
```

<div align="center">

<sub><i>One command, no key. `sim try` replays two real recorded runs: the swarm completes a working signup (gate passes), then hits a build where a deploy broke the submit and can't finish — each agent annotated with the exact pixel it gave up at (gate fails, exit 1). Set a key to run it live.</i></sub>

[![MIT License](https://img.shields.io/badge/license-MIT-black.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-black.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-436%20passing-black.svg)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-72%25-black.svg)](#contributing)
[![Backends](https://img.shields.io/badge/backend-Gemini%20·%20Holo%20·%20self--host-black.svg)](#bring-any-key)

**[▶ Watch the 2-min demo](https://simulationlabs.dev/demo/)** · **[See a real report](https://simulationlabs.dev/sample-report/)** · **[Why this exists](VISION.md)**

</div>

Unit tests prove your code runs. **They say nothing about whether a human can finish the flow.**
Simulation Labs sends a swarm of browser agents — some steady, some rushed, some fumbling a
small control on a phone — at a live page. Each one either completes the task or **fails at a
specific, reproducible pixel**. You get a completion rate, an abandonment heatmap over your real
page, and a non-zero exit code when it regresses.

---

## Quickstart

No account, no config, no signup:

```bash
pip install "git+https://github.com/SatyamDave/simulation-labs@main"
sim try
```

With **no key**, `sim try` instantly replays the two real recorded runs above — no browser
download, no network, a result in seconds. It's the honest way to see what the tool does before
you spend a key on it. (The full run streams each agent step-by-step; the summary is shown above.)

**Run it live.** `sim try --live` runs the swarm for real against the bundled flow. It needs a
model key — grab a **[free Gemini key](https://aistudio.google.com/apikey)** (no card, ~30
seconds); `sim try --live` prompts you to paste it on first run, or `export GEMINI_API_KEY=...`
once. The first live run also installs a headless Chromium (~150 MB, one time).

---

## Point it at *any* flow

The task is plain English, so the same engine tests any critical flow — not just signup.
Point it at a URL, describe the goal, and the swarm attempts it:

```bash
# SaaS signup
sim gate --url https://your-app.com/signup   --task "create an account with email and password"

# Multi-step checkout
sim gate --url https://shop.example.com/cart --task "buy the item in the cart with a test card and reach the receipt"

# Onboarding wizard
sim gate --url https://your-app.com/welcome  --task "complete onboarding: pick a plan, invite a teammate, land on the dashboard"
```

`sim gate` exits **`0`** when completion holds and **`1`** when it regresses — the whole contract,
on any flow. That non-zero exit is what blocks the merge:

```bash
sim gate --url https://your-app.com/signup --task "create an account"; echo "exit: $?"
# exit: 1   ← completion dropped below baseline; CI fails the build
```

It drops straight into CI:

```yaml
# .github/workflows/simulate.yml
- run: pip install "git+https://github.com/SatyamDave/simulation-labs@main"
- run: playwright install chromium
- run: sim gate --url ${{ env.PREVIEW_URL }} --task "create an account"
  env:
    GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

`sim init` writes that workflow and a `sim.yml` for you. `sim baseline` seeds the first green
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
| **Google Gemini** | `GEMINI_API_KEY` | Free tier runs `sim try --live` end to end |
| **H Company Holo** | `HAI_API_KEY` | Purpose-built computer-use model |
| **Self-hosted** | `MODEL_BACKEND=selfhost` + `MODEL_BASE_URL` | Any OpenAI-compatible vision endpoint |
| **Echo (offline)** | `MODEL_BACKEND=echo` | Deterministic, no network — for tests/CI dry-runs |

Drop a key in `.env` and it loads automatically. Nothing leaves your machine except the
screenshots you send to the model provider you chose. Installing the CLI pulls only what the CLI
needs; the server and billing stacks are optional extras (`pip install "simulation-labs[server]"`).

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
| **Misclick-prone** | coordinate noise on every click | fumbles small controls |

The controls set the ceiling; the degraded agents show you how far below it your real traffic
sits. When a deploy breaks the flow, **every** segment drops and the gate goes red — with the
exact pixel each one walked away at.

**What you get per run:** a completion rate, a survival curve, an abandonment heatmap painted
over your real screenshot, video receipts of each session, and grounded exit-interview
transcripts. See a full one: **[live sample report](https://simulationlabs.dev/sample-report/)**.

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

Everything crossing a module boundary is a typed contract, not a dict. The five commands are
`sim try`, `sim run`, `sim gate`, `sim baseline`, and `sim init`. 436 tests, 72% coverage,
MIT licensed.

## Contributing

Issues and PRs welcome — especially new behavioral segments, new model backends, and real-world
flows that break the gate in interesting ways. Start with **[CONTRIBUTING.md](CONTRIBUTING.md)**;
`pip install -e ".[dev]" && pytest` gets you a green suite. Security reports:
**[SECURITY.md](SECURITY.md)**.

## Work with us

Want to run Simulation Labs on your own funnel, partner, or compare notes on where your users
abandon? Open an [issue](https://github.com/SatyamDave/simulation-labs/issues) or email
**sdaveofficial@gmail.com**.

## License

MIT. Use it, fork it, ship it.

---

<div align="center">
<sub>Behavioral user research that <b>does</b>, not <b>says</b>. · <a href="https://simulationlabs.dev">simulationlabs.dev</a> · <a href="mailto:sdaveofficial@gmail.com">sdaveofficial@gmail.com</a></sub>
</div>
