# Ghostpanel Architecture

Simulation Labs is a swarm of **behavioral synthetic users**. Every other synthetic-user research tool simulates what users *say*; Simulation Labs simulates what users *do*. It points a swarm of computer-use agents at a live website with a real goal (sign up, check out, cancel). Each agent's **perception and actuation channels are mechanically degraded** to reproduce a real behavioral segment — coordinate noise for imprecise taps, tight step/time budgets for impatience, small phone viewports, constrained literal reading for a first-timer. They either complete the task or abandon at a specific recorded pixel. Output: a **completion rate**, a **survival curve**, an **abandonment heatmap**, **video receipts**, and **exit-interviews** grounded in each agent's real action trace.

---

## End-to-end data flow

```
Frontend (web/, Agent 4)
   │  POST /runs {target_url, task, persona_ids}
   │  WS  /ws/runs/{id}  ← RunEvent stream (live grid)
   ▼
Server / Orchestrator (src/ghostpanel/server/, Agent 3)  ── composition root wires everything
   │  for each persona:  asyncio task  (all share one browser + one Holo rate limiter)
   ▼
SessionRunner (src/ghostpanel/runner/, Agent 2)
   │  loop: screenshot ──► PersonaAgent.decide(obs) ──► execute pixel action ──► emit StepEvent
   ▼
PersonaAgent + HoloClient (src/ghostpanel/engine/, Agent 1)
   │  perturb screenshot (blur/downscale/CVD) ─► Holo Models API ─► parse Action ─► jitter coords
   ▼
   returns Action (TRUE viewport pixels) to the runner
   ...on finish → PersonaResult
       ├─► ReportBuilder (src/ghostpanel/report/, Agent 5) → RunReport (survival + heatmap + HTML)
       └─► VoiceEngine  (src/ghostpanel/voice/,  Agent 5) → exit-interview .wav
```

**A single run, step by step:**
1. The frontend `POST /runs` with the target URL, task, and chosen persona ids; gets back a `run_id` and opens `WS /ws/runs/{run_id}`.
2. The `SwarmManager` emits `RunStarted`, captures a clean `target.png`, and fans out **one `asyncio` task per persona** — all sharing the single Chromium `Browser` and single rate-limited `LiveHoloClient`.
3. Each `PlaywrightSessionRunner` creates its own browser **context** (isolated + video-recorded), navigates, and loops: screenshot → `PersonaAgent.decide(obs)` → execute the pixel action → emit a `StepEvent` (thumbnail + caption) → until success, budget exhaustion, or stuck.
4. Inside `decide`, the engine **perturbs a copy** of the screenshot (downscale → blur → CVD), sends it to Holo, parses the reply into an `Action`, **denormalizes** Holo's 0–1000 coords to true pixels, and **jitters** them by the persona's tremor sigma.
5. On finish, each persona yields a `PersonaResult`; the swarm builds a `RunReport` (survival curve + abandonment heatmap + offline HTML) and narrates exit interviews (Gradium `.wav` or text-only via Claude), then emits `RunFinished`.
6. The frontend folds the `RunEvent` stream into a live grid and, when finished, fetches `GET /runs/{id}/report` to render the report with video/voice receipts.

---

## The two golden rules

1. **Coordinates are true viewport pixels at the engine→runner boundary.** The engine returns `Action.x/.y` already denormalized (0–1000 → px) and tremor-jittered. The runner executes them verbatim with `page.mouse.click(x, y)` and **never rescales**. This works because every perturbation **preserves image dimensions** (blur/CVD change pixel values only; downscale resizes down then back up in place), so Holo's normalized grid always maps back to the real viewport.
2. **Everything crossing a module boundary is a frozen contract model**, never a bare dict/tuple. The five modules were built by five parallel agents on five branches that had to merge with zero conflicts — they code against `shared/ghostpanel_contracts/` (see `docs/CONTRACTS.md`), not each other's source.

---

## The five modules

| Module | Path | Responsibility |
|---|---|---|
| Engine | `src/ghostpanel/engine/` | Model client, personas, perturbations, prompts |
| Runner | `src/ghostpanel/runner/` | Playwright session loop, execute, detect, thumbnail |
| Orchestrator | `src/ghostpanel/server/` + `app.py` | FastAPI, WS hub, swarm, composition root |
| Frontend | `web/` | React live grid + report + offline demo |
| Voice + Report | `src/ghostpanel/voice/` + `report/` | Survival/heatmap report, exit interviews |

---

## Key invariants & semantics

- **Only `success` counts as completion.** `error` is infra failure (a crash, not a human "give up") and is **excluded from survival statistics** and the completion-rate denominator. The other outcomes — `step_budget`, `time_budget`, `stuck` — are genuine abandonments.
- **The swarm shares one Holo rate limiter** (free tier ~10 RPM) so a whole run stays within budget; a single `RateLimiter` token bucket is threaded into every persona's client.
- **One `chromium.launch()` + N contexts.** Contexts are cheap and isolated; each records its own `.webm`, flushed on `context.close()`.
- **Live events are the exact WS JSON.** The `RunEvent` discriminated-union (on `event`) is dumped to JSON, pushed over the socket, and `switch`ed on by the TS client with no schema negotiation.
- **Fail-soft everywhere on the demo path.** Narration, HTML rendering, thumbnails, per-persona crashes, voice/LLM calls are all individually guarded so one failure never poisons the run or the rest of the swarm.

---

## External integrations

- **H-Company Holo Models API** — OpenAI-compatible (`AsyncOpenAI(base_url, api_key)`); the screenshot goes as a base64 data URI in an `image_url` part. Model `holo3-1-35b-a3b`. It is a **reasoning model** and returns coords **normalized to a 0–1000 grid**.
- **Gradium** — TTS (`client.tts(setup, text)` with `output_format:"wav"`), optional voice cloning, and STT for live Q&A.
- **Anthropic (Claude)** — grounds the exit-interview script generation (`claude-sonnet-5` by default); degrades to a deterministic template without a key.
- **NemoClaw / OpenShell** (on `repeated-bathroom`) — a network-policy cage; route Holo inference through the gateway (`NEMOCLAW_GATEWAY_URL`) and enforce a browse-only policy in the browser context.

---

## Config & artifacts

Config is read from env / `.env` (`Settings`, `get_settings()`): `HAI_*` (Holo), `GRADIUM_API_KEY`, `ANTHROPIC_*`, `GHOSTPANEL_HOST/PORT/ARTIFACT_DIR`, `NEMOCLAW_*`. Artifacts land under `GHOSTPANEL_ARTIFACT_DIR/<run_id>/`: `target.png` (clean page shot), per-persona `.webm` video receipts, exit-interview `.wav`, `report.html`, and (on `repeated-bathroom`) `insights.json`. The FastAPI app serves them at `/artifacts` and the built SPA at `/`.
