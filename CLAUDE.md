# CLAUDE.md — Ghostpanel build guide (read this first)

> This repo is built by **five parallel agents on five branches** that must merge
> with **zero conflicts**. That only works if everyone obeys two rules:
>
> 1. **Write only inside the files/directories your agent OWNS** (ownership map below).
> 2. **Never edit `shared/ghostpanel_contracts/` or `pyproject.toml`** — they are frozen.
>    All cross-module communication goes through the frozen contracts.

If you are one of the five agents: open your `agents/AGENT_N_*.md`, then use this file
as the shared reference. Do **not** read another agent's source to do your job — code
against the contracts.

---

## What Ghostpanel is (one paragraph)

Ghostpanel is a swarm of **behavioral synthetic users**. Every synthetic-user research
tool simulates what users *say*; Ghostpanel simulates what users *do*. We point a swarm
of H-Company **Holo**-powered personas at a live website with a real goal (sign up, check
out, cancel). Each persona is a Holo agent whose **perception and actuation channels are
mechanically degraded** to model a real impairment — blur for low vision, coordinate noise
for tremor, tight step/time budgets for impatience, colour-vision filters, small viewports.
They either complete the task or abandon at a specific recorded pixel. Output: a **survival
curve**, an **abandonment heatmap**, **video receipts**, and **voice exit-interviews**
(Gradium cloned voices) grounded in each persona's real action trace. See `VISION.md`.

---

## Architecture & data flow

```
Frontend (web/, Agent 4)
   │  POST /runs {target_url, task, persona_ids}
   │  WS  /ws/runs/{id}  ← RunEvent stream (live grid)
   ▼
Server / Orchestrator (src/ghostpanel/server/, Agent 3)  ── composition root wires everything
   │  for each persona:  asyncio task
   ▼
SessionRunner (src/ghostpanel/runner/, Agent 2)
   │  loop: screenshot ──► PersonaAgent.decide(obs) ──► execute pixel action ──► emit StepEvent
   ▼
PersonaAgent + HoloClient (src/ghostpanel/engine/, Agent 1)
   │  perturb screenshot (blur/downscale/CVD) ─► Holo Models API ─► parse Action ─► jitter coords
   ▼
   returns Action (TRUE viewport pixels) to the runner
   ...on finish → PersonaResult
       ├─► ReportBuilder (src/ghostpanel/report/, Agent 5) → RunReport (survival + heatmap)
       └─► VoiceEngine  (src/ghostpanel/voice/,  Agent 5) → exit-interview .wav
```

**Golden rule on coordinates:** the engine returns `Action.x/.y` already in **true viewport
pixels** (tremor jitter + any smart_resize remap applied). The runner executes them verbatim
with `page.mouse.click(x, y)` and never rescales.

---

## FILE-OWNERSHIP MAP (no path appears twice)

| Agent | Branch | May create/edit ONLY | Also reads (never edits) |
|-------|--------|----------------------|--------------------------|
| **1 Engine** | `agent/engine` | `src/ghostpanel/engine/**`, `personas/**`, `tests/engine/**` | contracts, `fixtures/sample_screenshot.png` |
| **2 Runner** | `agent/runner` | `src/ghostpanel/runner/**`, `tests/runner/**` | contracts, `fixtures/hostile_form.html` |
| **3 Orchestrator** | `agent/server` | `src/ghostpanel/server/**`, `src/ghostpanel/app.py`, `tests/server/**` | contracts + all module public classes (imports only) |
| **4 Frontend** | `agent/web` | `web/**` | `fixtures/run.json`, `fixtures/events.jsonl`, contracts (for shapes) |
| **5 Voice+Report** | `agent/voice-report` | `src/ghostpanel/voice/**`, `src/ghostpanel/report/**`, `tests/voice/**`, `tests/report/**` | contracts, `fixtures/run.json` |

Skeleton files owned by **nobody** (already committed, do not edit): `shared/**`,
`pyproject.toml`, `.env.example`, `.gitignore`, `fixtures/**`, `tests/test_contracts.py`,
`CLAUDE.md`, `VISION.md`, `ROADMAP.md`, `README.md`, `agents/**`, all `__init__.py` under
`src/ghostpanel/` (the empty package markers — add your own new modules beside them).

> If two agents ever feel they need the same file, they don't — one of them needs a new file
> in their own directory, or a new contract. Escalate to Agent 3 rather than editing across
> the line.

---

## CONCRETE CLASS REGISTRY (so Agent 3 can import & wire)

Every module MUST expose exactly these names at these paths. Agent 3's composition root
imports them; if you rename one, the merge breaks. Constructors take what's shown.

| Contract (Protocol) | Concrete class → module path | Constructor |
|---------------------|------------------------------|-------------|
| `HoloClient` | `ghostpanel.engine.holo_client.LiveHoloClient` | `(api_key, base_url, model, rpm)` |
| `HoloClient` (tests) | `ghostpanel.engine.holo_client.FakeHoloClient` | `(scripted_actions=None)` |
| `PersonaAgent` | `ghostpanel.engine.persona_agent.HoloPersonaAgent` | `(persona: PersonaConfig, holo: HoloClient)` |
| `SessionRunner` | `ghostpanel.runner.session.PlaywrightSessionRunner` | `(browser, artifact_dir)` |
| `EventSink` | `ghostpanel.server.events.WebSocketEventSink` | `(run_id, hub)` |
| `EventSink` (tests) | `ghostpanel.runner.testing.CollectingEventSink` | `()` — owned by Agent 2 for its own tests |
| `VoiceEngine` | `ghostpanel.voice.gradium_voice.GradiumVoiceEngine` | `(api_key, artifact_dir, anthropic_key=None)` |
| `ReportBuilder` | `ghostpanel.report.builder.SurvivalReportBuilder` | `()` |
| persona loader | `ghostpanel.engine.personas.load_personas(ids=None) -> list[PersonaConfig]` | reads `personas/*.json` |

`isinstance(obj, HoloClient)` etc. work because the Protocols are `@runtime_checkable` — use
that in tests to assert you satisfy the contract.

---

## The frozen contracts (what you import)

```python
from ghostpanel_contracts import (
    PersonaConfig, Observation, Action, ActionType, ScrollDirection,
    StepRecord, PersonaResult, PersonaOutcome,
    RunReport, SurvivalPoint, HeatPoint,
    RunEvent, RunStarted, PersonaStarted, StepEvent, PersonaFinished, RunFinished,
    HoloClient, PersonaAgent, SessionRunner, EventSink, VoiceEngine, ReportBuilder,
)
```

Read `shared/ghostpanel_contracts/contracts.py` for field-level docs. Highlights:
- `Action.type` is an `ActionType`; coordinates are true viewport pixels; `caption` is what
  the UI tile shows ("Clicking Sign up").
- `RunEvent` is a **discriminated union on `event`** — this is the exact JSON on the WebSocket.
- `PersonaOutcome`: `success | step_budget | time_budget | stuck | error`. Only `success`
  counts as completion; `error` is infra failure (exclude from survival stats).

---

## Verified integration facts (from research — trust these)

### H Company Holo Models API (Agent 1)
- **OpenAI-compatible.** `from openai import OpenAI; OpenAI(base_url=HAI_BASE_URL, api_key=HAI_API_KEY)`.
- Send the screenshot as a base64 **data URI** in an `image_url` content part (exactly like GPT-4o vision).
- Model `holo3-1-35b-a3b` (Apache-2.0). Free tier **10 RPM** → the whole swarm shares one
  rate limiter (`HAI_RPM`). Max 5 images per request; context 65k.
- **Localizer prompt** (returns `Click(x, y)`): *"Localize an element on the GUI image according
  to my instructions and output a click position as Click(x, y) with x num pixels from the left
  edge and y num pixels from the top edge."*
- **Navigation** action space to parse: click / write / scroll / go_back / refresh / wait /
  goto / restart / answer (map to `ActionType`).
- **COORDINATE SPACE (verified live):** the hosted Holo3.1 API returns coords **normalized to a
  0–1000 grid**, NOT absolute pixels. `LiveHoloClient` denormalizes them to true pixels
  (`x/1000*w`, `y/1000*h`) internally — downstream code (runner) receives true viewport pixels and
  executes verbatim. Confirmed: a button at true centre (547,430) in a 1280×800 shot came back as
  Click(426,536) → 545,429. Also keep image **dimensions constant** through perturbation (blur/CVD
  change pixel values only; downscale = resize down then back up in place) so the denormalization
  target stays the real viewport size. `FakeHoloClient` returns pixel coords directly (no denorm).
- Refs: `hub.hcompany.ai/quickstart`, `github.com/hcompai/hai-cookbook` (`utils/localization.py`,
  `utils/navigation.py`), `github.com/hcompai/surfer-h-cli` (agent-loop reference).

### Playwright (Agent 2)
- `page.mouse.click(x, y)` uses **viewport CSS pixels** = Holo's output space. Also
  `mouse.wheel`, `keyboard.type`. Screenshot via `page.screenshot()` (PNG bytes).
- Parallelism: **one `chromium.launch()` + N `browser.new_context()`** (cheap, isolated).
- **Video receipts:** set `record_video_dir` + `record_video_size` on the *context*; video
  flushes to `.webm` on `context.close()`; `await page.video.save_as(path)` for a named file.
- Use the **async** API + `asyncio.gather`. Headless for the swarm (frames stream to our own UI).

### Gradium voice (Agent 5)
- `pip install gradium`; `GRADIUM_API_KEY` (`gd-...`). `client.tts(setup={"voice_id":..,
  "output_format":"wav"}, text=..)`; `client.stt_realtime(...)`; `gradium.voices.create(client,
  audio_file=.., name=..)` (clone from ~10s). Semantic VAD rides inside the STT stream (`step` msgs).

### NemoClaw / NVIDIA (Agent 3, optional stretch)
- OpenShell sandbox runs in Docker on Mac; **on-device Nemotron needs a GPU — out of scope.**
- Integration = route Holo inference through OpenShell's policy gateway (set `NEMOCLAW_GATEWAY_URL`,
  point the Holo `base_url` at it). Pull the real YAML policy schema live from
  `docs.nvidia.com/nemoclaw/latest/llms.txt` — **do not fabricate** a policy file.

---

## Conventions

- **Python 3.11+**, async everywhere in engine/runner/server. Type-hint public functions.
- Everything crossing a module boundary is a **contract model** — never a bare dict/tuple.
- Config from env (`python-dotenv`); never hardcode keys. Read `.env.example` for names.
- Artifacts (`.webm`, `.wav`, reports) go under `GHOSTPANEL_ARTIFACT_DIR/<run_id>/`.
- Tests live in `tests/<yourmodule>/`; don't touch `tests/test_contracts.py`.
- Keep it demo-first: the live grid must look alive. Emit a `StepEvent` (with a thumbnail and a
  human `caption`) on **every** step.

## Local setup (each agent)

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium          # Agent 2/3 only
cp .env.example .env                 # fill in keys
pytest tests/test_contracts.py -q    # must stay green
```

## Definition of done (per agent)

Your module (a) exposes the exact class names in the registry, (b) satisfies its Protocol
(`isinstance` check passes), (c) has passing tests under `tests/<module>/`, (d) keeps
`tests/test_contracts.py` green, (e) touched **only** your owned paths. See your
`agents/AGENT_N_*.md` for the concrete task list and per-module verification.
