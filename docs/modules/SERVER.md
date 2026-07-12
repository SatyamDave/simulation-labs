# Server / Orchestrator Module — `src/ghostpanel/server/` + `src/ghostpanel/app.py`

> **Owner:** Agent 3 (`agent/server`) · **Registry classes:** `WebSocketEventSink`, plus `create_app` composition root

Agent 3 is pure orchestration. It owns no engine/runner/report/voice logic itself; it **wires the concrete implementations authored by the other agents into one running FastAPI process**, runs N persona sessions in parallel over a single shared browser, streams live events over WebSockets, and on completion builds a report + triggers voice exit-interviews.

**Swarm model:** one `chromium.launch()` + **N browser contexts** (one per persona, created inside the runner), all sharing a single rate-limited `LiveHoloClient` so a run stays within the free-tier RPM budget.

---

## 1. Module map

| File | Role |
|---|---|
| `config.py` | Frozen `Settings` dataclass from env/`.env`; `get_settings()` (`lru_cache`). |
| `runs.py` | In-memory `RunRegistry` + `RunRecord` + `RunStatus`. |
| `ws.py` | `WebSocketHub` (per-run pub/sub + replay ring buffer) + `WebSocketEventSink`. |
| `events.py` | Re-export shim so `ghostpanel.server.events.WebSocketEventSink` resolves. |
| `api.py` | `APIRouter` — all HTTP + the WS route. |
| `swarm.py` | `SwarmManager` — the actual orchestrator. |
| `main.py` | Console entrypoint `ghostpanel` → uvicorn `app:create_app` (factory). |
| `app.py` | **Composition root** — the only module importing concrete classes from every subsystem. |

---

## 2. HTTP + WebSocket API (`api.py`)

`/artifacts` and `/` are **not** routes — they are app-level `StaticFiles` mounts in `create_app`.

| Method / Path | Behaviour |
|---|---|
| `GET /healthz` | `{"status":"ok"}` liveness. |
| `GET /personas` | Full roster: `[p.model_dump() for p in load_personas(None)]` — the launch form's source of truth. |
| `POST /runs` | Body `{target_url, task, persona_ids?}` → `{run_id}`. **503** if `app.state.swarm` is `None` (before lifespan startup). Delegates to `SwarmManager.start_run`, returns immediately. |
| `GET /runs` | List of `RunRecord.summary()`. |
| `GET /runs/{id}/report` | Full `RunReport` JSON. **404** unknown id; **425 Too Early** if the report isn't cached yet. |
| `WS /ws/runs/{id}` | Accept → `hub.subscribe(id)` (queue pre-loaded with the full backlog) → pump each event as JSON → break on terminal `run_finished` → always `unsubscribe` in `finally`. |

Because subscribe pre-loads the backlog, a client connecting *after* a run finished still replays the entire stream and the closing `run_finished`.

**Static mounts (in `app.py`):** `/artifacts` → `StaticFiles(artifact_dir, check_dir=False)` (serves `.webm`, `.wav`, `report.html`, `target.png`); `/` → `StaticFiles(web/dist, html=True)` mounted **last** so API routes win over the catch-all.

---

## 3. Run registry (`runs.py`)

Process-local, single-event-loop store. `RunStatus`: `PENDING`/`RUNNING`/`FINISHED`/`ERROR`. `RunRecord` holds ids, `status`, `report`, `error`, and `task_handle` (the driving asyncio task, held so tests/shutdown can await it). `RunRegistry`: `create` (starts at **`RUNNING`**), `get`, `set_report` (→ `FINISHED`), `set_error` (→ `ERROR`), `list`, `all_records`. `RunRecord.summary()` feeds `GET /runs` with `completion_rate` + `persona_count`.

---

## 4. WebSocket hub + sink (`ws.py`)

`WebSocketHub(buffer_size=2000)`:
- `_buffers: dict[run_id, deque(maxlen=2000)]` — bounded replay ring buffer per run.
- `_subscribers: dict[run_id, set[Queue]]`.
- `publish(run_id, event)` — appends to buffer, `put_nowait` to every live subscriber (iterates a snapshot). **Declared `async` but has no `await`** — deliberately await-free so all persona tasks can fan events in concurrently under `asyncio.gather` with no interleaving hazard.
- `subscribe(run_id)` — new `Queue` **pre-loaded with the current backlog**, registered, returned (the replay mechanism).
- `unsubscribe` / `buffer` (snapshot).

`WebSocketEventSink(run_id, hub)` — the concrete `EventSink`: `emit(event)` = `hub.publish(run_id, event.model_dump(mode="json"))`. `model_dump(mode="json")` guarantees bytes never reach the wire and enums serialize to strings.

---

## 5. `SwarmManager` (`swarm.py`)

Everything concrete is injected via factories so wiring is swappable: `AgentFactory` (→ `HoloPersonaAgent`), `RunnerFactory` (→ `PlaywrightSessionRunner`), `PredicateFactory` (returns a `#ok`-visible predicate for `hostile_form.html`, else `None`), `VoiceEngineFactory`. Constructor is keyword-only; defaults `report_builder=SurvivalReportBuilder()` and `voice_success_ids={"ai-agent"}` (personas that get a voice interview even on success).

**`start_run(target_url, task, persona_ids=None) -> str`:** `run_id = uuid4().hex[:12]`; `load_personas(persona_ids)`, falling back to the **full roster** if empty (a run is never empty); `registry.create(...)`; schedules `asyncio.create_task(self._execute(...))` on the record's `task_handle`; returns `run_id` immediately.

**`_execute(...)`** (wrapped so a run never crashes the server):
1. Emit `RunStarted(run_id, target_url, task, personas)`.
2. `_capture_target` — best-effort clean screenshot to `<run_id>/target.png` for the heatmap overlay.
3. **Parallel fan-out:** `results = await asyncio.gather(*(self._run_one(...) for persona in personas))` — one coroutine per persona, all sharing the one browser + one Holo client.
4. `report = report_builder.build(...)`.
5. `_narrate(...)` — fills exit-interview text/audio, **mutating `PersonaResult`s in place**.
6. `write_html_report(...)` (guarded).
7. `registry.set_report(...)` → `FINISHED`.
8. Emit `RunFinished(run_id, report_url=f"/artifacts/{run_id}/report.html", completion_rate=...)`.

**Error path:** `registry.set_error(...)`, then **still** emit a terminal `RunFinished(completion_rate=0.0)` so WS clients always close cleanly, then re-raise (surfaces on `task_handle`).

**`_run_one(...)`** builds a fresh per-persona sink, then `agent = agent_factory(persona, holo_client, task)`, `runner = runner_factory(browser, artifact_dir, predicate)`, `return await runner.run(...)`. Any hard failure is converted to `PersonaResult(outcome=ERROR, ...)` so **one crash never poisons `asyncio.gather`** for the rest of the swarm.

**`_narrate(...)`** attaches exit-interview narration to non-success personas (plus `voice_success_ids`): optionally a per-run Gradium engine (`voice_engine_factory(run_dir)`), else text-only via `write_exit_interview(..., anthropic_key=...)`. Every voice/LLM call is individually try/excepted.

---

## 6. Config (`config.py`)

`Settings` — `@dataclass(frozen=True)`. Env vars (default):

| Field | Env | Default |
|---|---|---|
| `hai_api_key` | `HAI_API_KEY` | `""` |
| `hai_base_url` | `HAI_BASE_URL` | `https://api.hcompany.ai/v1/` |
| `hai_model` | `HAI_MODEL` | `holo3-1-35b-a3b` |
| `hai_rpm` | `HAI_RPM` | `5.0` (`.env.example` ships `10`) |
| `gradium_api_key` | `GRADIUM_API_KEY` | `""` |
| `anthropic_api_key` | `ANTHROPIC_API_KEY` | `""` |
| `anthropic_model` | `ANTHROPIC_MODEL` | `claude-sonnet-5` |
| `host` / `port` | `GHOSTPANEL_HOST` / `_PORT` | `127.0.0.1` / `8000` |
| `artifact_dir` | `GHOSTPANEL_ARTIFACT_DIR` | `<repo>/artifacts` |
| `nemoclaw_gateway_url` | `NEMOCLAW_GATEWAY_URL` | `""` |

Computed: `holo_base_url` returns `nemoclaw_gateway_url` if set (routes Holo through the NemoClaw policy gateway) else `hai_base_url`; `has_gradium` gates voice. `get_settings()` is `lru_cache(maxsize=1)` — tests pass an explicit `Settings` to avoid the process-wide cache.

**Artifact layout:** `GHOSTPANEL_ARTIFACT_DIR/<run_id>/` holds `target.png`, `report.html`, per-persona `.webm` receipts, and exit-interview `.wav`.

---

## 7. Composition root (`app.py`)

`create_app(*, settings=None, holo_client=None, enable_voice=None, launch_browser=True)`. The three keyword-only test seams inject a `FakeHoloClient`, force voice off, or skip the real Chromium.

Boot: resolves settings, `mkdir` the artifact dir, builds `FastAPI(lifespan=...)`, adds permissive CORS (for the Vite dev port), eagerly builds browser-independent state (`WebSocketHub`, `RunRegistry`, `app.state.swarm = None`), `include_router(router)`, then mounts `/artifacts` and (if present) `/`.

**`lifespan` startup:** launch **one** shared headless Chromium; construct **one** shared `LiveHoloClient` (single shared `RateLimiter`); if `enable_voice` and `has_gradium`, define a `voice_factory(run_dir)` → `GradiumVoiceEngine`; build `SwarmManager(...)` and assign `app.state.swarm`. **Shutdown:** close browser + stop Playwright (both suppressed).

**`main.py`:** `uvicorn.run("ghostpanel.app:create_app", factory=True, host=..., port=...)` — factory calls `create_app()` with all defaults (real browser, real Holo, voice auto-detected).

---

## 8. Cross-cutting gotchas

- `app.state.swarm` is `None` until `lifespan` startup — `POST /runs` returns 503 before then; `TestClient` must be used as a context manager to trigger startup.
- `get_settings()` is `lru_cache`d — pass explicit `Settings` in tests.
- Registry status starts at `RUNNING` (not `PENDING`).
- `RunFinished` is always emitted (success and error), giving the WS route a guaranteed terminal event.
- Replay-first WS: connect after finish and still replay; the 2000-event ring buffer can drop the earliest events on very long runs.
- Per-persona error isolation + best-effort narration/HTML/screenshot all swallow exceptions.
- `events.py` is only a re-export shim; the real classes live in `ws.py`.
