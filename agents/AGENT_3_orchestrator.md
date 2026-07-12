# AGENT 3 — Orchestrator (FastAPI + swarm + composition root)

**Branch:** `agent/server`   **You own:** `src/ghostpanel/server/**`, `src/ghostpanel/app.py`,
`tests/server/**`   **Never edit:** `shared/**`, `pyproject.toml`, other modules' source.

You are the **composition root** — the ONLY place that imports concrete classes from the other
modules and wires them together. You run the swarm, broadcast live events to the frontend, and
serve artifacts + the report. Read `CLAUDE.md` (class registry — import exactly those names) and
the contracts first.

## Mission

Expose an HTTP+WebSocket API that: starts a run, launches N persona sessions in parallel against
one shared browser + one shared rate-limited Holo client, streams `RunEvent`s live, and on
completion builds the report and triggers voice exit-interviews.

## Files to create

```
src/ghostpanel/
  app.py           # create_app() FastAPI factory + the composition root (wire concrete classes)
  server/
    main.py        # def main(): uvicorn.run(create_app(), host, port)  (entrypoint)
    api.py         # routes: POST /runs, GET /runs/{id}/report, GET /runs (list), static/artifacts
    ws.py          # WebSocketHub + WebSocketEventSink (registry EventSink)
    swarm.py       # SwarmManager: asyncio.gather personas, aggregate results, build report+voice
    config.py      # env config (dotenv): HAI_*, GRADIUM_*, ANTHROPIC_*, GHOSTPANEL_*, NEMOCLAW_*
    runs.py        # in-memory run registry (RunReport cache, per-run event buffer)
tests/server/
  test_api.py
  test_swarm.py
```

## Contracts you implement / consume

- **Implement (registry):** `server.ws.WebSocketEventSink(run_id, hub)` — an `EventSink` whose
  `emit()` fans the event out to all WS clients subscribed to `run_id` (and buffers it so late
  subscribers can catch up).
- **Import & wire (from the registry in CLAUDE.md):**
  - `engine.holo_client.LiveHoloClient` (shared, one rate limiter for the whole swarm)
  - `engine.persona_agent.HoloPersonaAgent`, `engine.personas.load_personas`
  - `runner.session.PlaywrightSessionRunner`
  - `report.builder.SurvivalReportBuilder`
  - `voice.gradium_voice.GradiumVoiceEngine`
- **Consume models:** `PersonaConfig`, `PersonaResult`, `RunReport`, all `RunEvent` members.

> Until the other branches merge, import at call-time inside `create_app`/`SwarmManager` (or guard
> imports) so your own tests can run with fakes. Use `engine.holo_client.FakeHoloClient` and a
> stub runner in tests — do not require live keys for `pytest`.

## Tasks

### 1. `config.py`
Load `.env`; expose a `Settings` object (pydantic-settings or a plain dataclass) with all env
vars from `.env.example`. One shared `LiveHoloClient` built from `HAI_*` + `HAI_RPM` (single
rate limiter shared by every persona).

### 2. `ws.py` — live event fan-out
- `WebSocketHub`: `subscribe(run_id, websocket)`, `unsubscribe(...)`, `publish(run_id, event)`,
  and a per-run ring buffer so a client connecting mid-run gets the backlog first.
- `WebSocketEventSink(run_id, hub)`: `async emit(event)` → serialize the `RunEvent`
  (`event.model_dump(mode="json")`) → `hub.publish(run_id, ...)`. Must be safe under
  `asyncio.gather` (many personas emitting concurrently).

### 3. `swarm.py` — `SwarmManager`
- `async def start_run(target_url, task, persona_ids) -> run_id`: create `run_id`, load personas,
  emit `RunStarted`, then `asyncio.gather` one `PlaywrightSessionRunner.run(...)` per persona over
  **one shared `Browser`** and the **shared Holo client**. Each session gets a
  `WebSocketEventSink(run_id, hub)`.
- On all-settled: call `SurvivalReportBuilder.build(...)` → `RunReport`; kick off
  `GradiumVoiceEngine.exit_interview(...)` per non-success persona (fire-and-forget or awaited —
  your call; don't block the grid). Cache the report in `runs.py`; emit `RunFinished` with the
  report URL.
- Respect the shared rate limiter so the swarm never exceeds `HAI_RPM` in aggregate.

### 4. `api.py` — routes
- `POST /runs` `{target_url, task, persona_ids?}` → `{run_id}` (starts the swarm in the background).
- `GET  /ws/runs/{run_id}` (WebSocket) → subscribe; replay buffer then live `RunEvent`s.
- `GET  /runs/{run_id}/report` → the cached `RunReport` JSON.
- `GET  /runs` → list of runs (id, target, completion_rate).
- `GET  /artifacts/...` → serve `.webm`/`.wav`/report HTML from `GHOSTPANEL_ARTIFACT_DIR`
  (use `StaticFiles`). Also mount the built frontend (`web/dist`) at `/` if present.
- Enable permissive CORS for local dev (frontend on a different Vite port).

### 5. `app.py` — composition root + `main.py`
- `create_app() -> FastAPI`: build `Settings`, the shared Holo client, the `WebSocketHub`, launch
  Playwright + `Browser` on startup (`@app.on_event("startup")`), construct the `SwarmManager` with
  all wired concrete classes, include the router. Close the browser/playwright on shutdown.
- `main.py`: `def main(): uvicorn.run("ghostpanel.app:create_app", factory=True, host=..., port=...)`.

### 6. NemoClaw / NVIDIA challenge (OPTIONAL stretch)
If `NEMOCLAW_GATEWAY_URL` is set, build the shared Holo client with `base_url` pointing at the
OpenShell gateway so inference is policy-governed. Add a `docs/nemoclaw/` note (in your own path —
e.g. `src/ghostpanel/server/nemoclaw.md`) explaining the setup and **paste the real YAML policy
pulled live** from `docs.nvidia.com/nemoclaw/latest/llms.txt` (do NOT fabricate). Keep it fully
optional — never a hard dependency for the core demo.

## Verification (must pass before merge)

```bash
pytest tests/server/ tests/test_contracts.py -q
```
- `test_swarm.py`: with `FakeHoloClient` + a stub/`PlaywrightSessionRunner` against
  `fixtures/hostile_form.html` (headless), run 2 personas; assert a `RunReport` is produced,
  `RunStarted`→…→`RunFinished` events reached a `CollectingEventSink`/test WS, and
  `completion_rate` is in `[0,1]`.
- `test_api.py`: FastAPI `TestClient` — `POST /runs` returns a `run_id`; after the run,
  `GET /runs/{id}/report` returns valid `RunReport` JSON; a WS client receives events.
- `isinstance(WebSocketEventSink(...), EventSink)` is `True`.
- **Manual live demo:** `python -m ghostpanel.server.main`, `POST /runs` against the hostile form,
  open the frontend, watch the grid.

## Done when
The whole system runs from a single entrypoint, the WS streams live events, the report endpoint
works, tests are green with fakes (no keys needed), and you touched only your paths.
