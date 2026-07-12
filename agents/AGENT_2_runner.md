# AGENT 2 — Runner (Playwright session)

**Branch:** `agent/runner`   **You own:** `src/ghostpanel/runner/**`, `tests/runner/**`
**Never edit:** `shared/**`, `pyproject.toml`, other modules.

You drive **one** persona's real browser session end-to-end. You do not know or care what a
persona *is* — you receive a `PersonaAgent` and call `.decide()`. Read `CLAUDE.md` (Playwright
facts, coordinate golden rule) and the contracts first. Do **not** read other modules' source;
test against `ghostpanel.engine.holo_client.FakeHoloClient` is fine (it's in the registry) — or
write your own tiny stub agent to stay fully decoupled.

## Mission

Given a `PersonaConfig`, a `PersonaAgent`, a target URL, a task, and an `EventSink`: launch a
browser context, run the perceive→decide→execute loop, stream live events, record a video, and
return a `PersonaResult`.

## Files to create

```
src/ghostpanel/runner/
  session.py     # PlaywrightSessionRunner  (implements SessionRunner)
  execute.py     # execute_action(page, action) — maps Action → Playwright calls
  detect.py      # success / stuck / loop detection helpers
  thumbnail.py   # png bytes → small JPEG data URI for StepEvent.thumbnail_b64
  testing.py     # CollectingEventSink (registry) + a StubPersonaAgent for tests
tests/runner/
  test_execute.py
  test_session.py
```

## Contracts you implement / consume

- **Implement:** `SessionRunner` → `PlaywrightSessionRunner(browser, artifact_dir)`.
- **Provide (registry):** `runner.testing.CollectingEventSink()` — an `EventSink` that stores
  emitted events in a list (used by Agent 3 tests and yours).
- **Consume:** `PersonaAgent.decide(obs, history)`, `EventSink.emit(event)`, and the models
  `Observation`, `Action`, `ActionType`, `ScrollDirection`, `StepRecord`, `PersonaResult`,
  `PersonaOutcome`, plus event models `PersonaStarted`, `StepEvent`, `PersonaFinished`.

`PlaywrightSessionRunner` takes a **live Playwright `Browser`** (Agent 3 launches it once and
shares it) and creates one **context per session**.

## Tasks

### 1. `execute.py` — `async def execute_action(page, action: Action) -> None`
Map each `ActionType` to Playwright (coords are already true viewport pixels — **never rescale**):
- `CLICK` → `await page.mouse.click(action.x, action.y)`
- `WRITE` → click `(x, y)` then `await page.keyboard.type(action.text)`; press `Enter` (matches
  Holo's WriteElementAction semantics)
- `SCROLL` → `await page.mouse.wheel(dx, dy)` per `action.direction`
- `GO_BACK` → `page.go_back()`; `REFRESH` → `page.reload()`; `GOTO` → `page.goto(action.url)`
- `WAIT` → `await asyncio.sleep(min(action.seconds or 2, 10))`
- `RESTART` → `page.goto(target_url)` (session remembers its start url)
- `ANSWER` → no-op here; the loop treats it as "persona declares done"

### 2. `session.py` — `PlaywrightSessionRunner.run(persona, agent, target_url, task, sink, run_id)`
1. `context = await browser.new_context(viewport=persona.viewport.model_dump(),
   record_video_dir=<artifact_dir>/<run_id>, record_video_size=persona.viewport...)`.
2. `page = await context.new_page()`; `await page.goto(target_url)`; emit `PersonaStarted`.
3. Loop `for step in range(persona.max_steps)` under an overall `asyncio.wait_for(...,
   persona.deadline_s)`:
   - `png = await page.screenshot()`; build `Observation`.
   - `action = await agent.decide(obs, history)`.
   - Build a `StepRecord` (+ thumbnail via `thumbnail.py`); append to results; **emit `StepEvent`**
     (with `caption`, `thumbnail_b64`, `x/y`) — this is what makes the grid feel alive.
   - If `action.type == ANSWER` or `detect.is_success(page)` → outcome `SUCCESS`, break.
   - If `detect.is_stuck(history)` (e.g. same click coord/URL repeated N times, no DOM change) →
     outcome `STUCK`, record `failure_coords`, break.
   - `await execute_action(page, action)`; `history.append(action.caption)`.
4. Exhausted steps → `STEP_BUDGET`; `asyncio.TimeoutError` → `TIME_BUDGET`; exception → `ERROR`.
5. On finish: set `failure_coords`/`failure_step`/`failure_reason` from the last meaningful step,
   `await context.close()` (flushes video), `await page.video.save_as(<named .webm>)`, emit
   `PersonaFinished`, return `PersonaResult` (with `video_path`, `duration_s`, `steps`).

**Success predicate:** default is a callable you accept (Agent 3 can pass one); for the bundled
`fixtures/hostile_form.html`, success = the `#ok` element is visible. Provide a sensible default
(look for a success-y element / URL change) and allow override.

### 3. `detect.py`
- `is_stuck(history, window=3)` — repeated identical captions/coords ⇒ giving up.
- `is_success(page, predicate=None)` — run the predicate or a default heuristic.

### 4. `thumbnail.py`
`to_thumb_data_uri(png_bytes, max_w=320) -> str` — downscale with Pillow, JPEG-encode, return
`data:image/jpeg;base64,...`. Keep it small; it goes over the WebSocket every step.

### 5. `testing.py`
- `CollectingEventSink` (registry): `async emit(event)` appends to `self.events`.
- `StubPersonaAgent(persona, script)` — returns scripted `Action`s so `test_session.py` runs with
  no engine/network. (You may instead import `FakeHoloClient` + `HoloPersonaAgent`; your call —
  but keep the test hermetic.)

## Verification (must pass before merge)

```bash
playwright install chromium
pytest tests/runner/ tests/test_contracts.py -q
```
- `test_execute.py`: against a `data:`/local page, assert a `CLICK` lands (e.g. a JS click
  handler flips a flag readable via `page.evaluate`).
- `test_session.py` (the important one): launch Chromium headless, run a `StubPersonaAgent`
  scripted to click the decoy then quit against `fixtures/hostile_form.html`; assert:
  - a `.webm` file is produced and `PersonaResult.video_path` points to it;
  - `StepEvent`s were emitted to a `CollectingEventSink` (≥1, with captions + thumbnails);
  - a budget-exhausting script yields `PersonaOutcome.STEP_BUDGET`;
  - a success script (fills email+promo, submits, `#ok` visible) yields `SUCCESS`.
- `isinstance(PlaywrightSessionRunner(...), SessionRunner)` is `True`.

## Done when
Registry classes at exact paths, Protocol satisfied, video + events proven in a headless test,
only your paths touched. Agent 3 will construct you with a shared `Browser` and its
`WebSocketEventSink`.
