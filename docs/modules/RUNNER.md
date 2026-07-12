# Runner Module — `src/ghostpanel/runner/`

> **Owner:** Agent 2 (`agent/runner`) · **Registry class:** `PlaywrightSessionRunner`

The runner drives **one persona's browser session end to end**. Agent 3 launches a single Chromium `Browser` once and shares it; this runner creates one browser **context** per session (cheap, isolated), records a video, runs the *perceive → decide → execute* loop, streams `StepEvent`s, and returns a `PersonaResult`. It is deliberately **mechanical** — it never roleplays a persona; all impairment (blur, tremor, CVD, impatience) is the engine's job.

Interface fixed by the frozen `SessionRunner` protocol:
```python
async def run(self, persona, agent, target_url, task, sink, run_id) -> PersonaResult
```

> ⚠️ **Two versions of the session loop exist.** The **`main`** working tree enforces patience as **real wall-clock** (`asyncio.wait_for(loop, timeout=deadline_s)`), so slow Holo calls burn the persona's deadline. The **simulated-clock** fix (persona patience burns think-time + page-time, *not* API latency) lives on branch **`debug`** / `origin/main` as commit `416e488` and is **not merged into local `main`**. Both are documented below (§2 = `main`, §7 = the fix).

---

## 1. Core loop

```
screenshot (raw PNG)
   → build Observation
   → PersonaAgent.decide(obs, history) → Action (true viewport pixels)
   → emit StepEvent (caption + thumbnail)
   → terminal checks (answer / success predicate / stuck)
   → execute pixel action against Playwright
   → append caption to history
   → repeat until success / step_budget / time_budget / stuck / error
```

---

## 2. `session.py` — `PlaywrightSessionRunner`

`__init__(browser, artifact_dir, success_predicate=None)` — stores the shared `Browser`, coerces `artifact_dir` to `Path`, and an optional per-run `SuccessPredicate`. `isinstance(runner, SessionRunner)` holds structurally.

Helpers:
- `_default_caption(action)` — UI caption when the agent didn't supply one (`"clicking (x, y)"`, `"typing 'text'[:24]"`, `"scrolling down"`, `"going to url"`, `"waiting"`, `"done"`, else the enum string).
- `_REASONS` — non-success outcome → human `failure_reason` fallback (`step_budget`→"ran out of steps", `time_budget`→"ran out of time", `stuck`→"stuck in a loop", `error`→"session error").

### `run(...)` algorithm

**Setup:** stopwatch `start = time.monotonic()`; empty `steps` and `history` (captions only); a mutable `state` dict holding `outcome`/`failure_coords`/`failure_step`/`failure_reason` (**a dict so partial terminal state survives an `asyncio.wait_for` cancellation**); `video_dir = artifact_dir/run_id`; then:
```python
context = await self.browser.new_context(
    viewport=persona.viewport.model_dump(),
    record_video_dir=str(video_dir),
    record_video_size=viewport,          # video matches what the persona "saw"
)
page = await context.new_page()
```

**Inner `_loop()`** — `for step in range(persona.max_steps)`:
1. `png = await page.screenshot()` (raw, un-perturbed).
2. `obs = Observation(raw_png=png, viewport=persona.viewport, step_index=step, url=page.url)`.
3. `action = await agent.decide(obs, history)` — **already true viewport pixels**.
4. `caption = action.caption or _default_caption(action)`; `thumb = to_thumb_data_uri(png)`.
5. Append `StepRecord`, then `await sink.emit(StepEvent(..., x=action.x, y=action.y))`.
6. **Terminal checks (evaluated on the frame just observed, *before* actuating):** `ANSWER` action → `SUCCESS`; `is_success(page, predicate)` → `SUCCESS`; `is_stuck(history)` → `STUCK` (records `failure_coords`/`failure_step`/reason).
7. **Actuate:** `RESTART` is rewritten to inject the session's `target_url`; `await execute_action(page, exec_action)`; only then `history.append(caption)` (so `is_stuck` at step N sees steps 0..N-1).
8. Loop exhausts without a terminal return → `STEP_BUDGET`.

**Outer orchestration:**
```python
await page.goto(target_url)          # before PersonaStarted, before the loop
video = page.video                   # recording handle, valid after navigation
await sink.emit(PersonaStarted(...))
try:
    await asyncio.wait_for(_loop(), timeout=persona.deadline_s)   # main: real wall clock
except asyncio.TimeoutError:
    state["outcome"] = PersonaOutcome.TIME_BUDGET
except Exception as exc:
    state["outcome"] = PersonaOutcome.ERROR
    state["failure_reason"] = f"{type(exc).__name__}: {exc}"[:200]
finally:
    ...
```

**`finally` (always runs):**
- **Failure-locus backfill:** for any non-`SUCCESS` outcome with steps, fill `failure_coords` from the last action's coords, `failure_step` from `steps[-1].step`, and `failure_reason` from `_REASONS` if still empty — so even a `time_budget`/`error` result points at *where* it died.
- **Video finalization:** `await context.close()` (**this is what flushes the `.webm`**), then `await video.save_as(video_dir/f"{persona.id}.webm")`; fallbacks: `video.path()` → `None`. All teardown errors swallowed.

**Assemble result:** emit `PersonaFinished(...)` then return `PersonaResult(...)` with `duration_s = time.monotonic() - start` (wall-clock on `main`). `transcript`/`audio_path` left for Agent 5.

### Outcome matrix

| Outcome | Trigger |
|---|---|
| `SUCCESS` | `ANSWER` emitted, or `is_success` predicate true (before actuating) |
| `STUCK` | last 3 captions identical (`is_stuck`) |
| `STEP_BUDGET` | `range(max_steps)` exhausts without a terminal return |
| `TIME_BUDGET` | `asyncio.wait_for(timeout=deadline_s)` raises `TimeoutError` |
| `ERROR` | any exception in setup/goto/loop, or `state["outcome"]` still `None` |

---

## 3. `execute.py` — pixel-action → Playwright

**Golden rule:** `action.x/.y` are already TRUE viewport pixels; execute verbatim with `page.mouse.click(x, y)` — **never rescale.** Constants: `_SCROLL_STEP = 600`, `_MAX_WAIT_S = 10.0`.

| ActionType | Playwright call | Notes |
|---|---|---|
| `CLICK` | `page.mouse.click(x, y)` | only if both coords set, else no-op |
| `WRITE` | `mouse.click(x,y)` → `keyboard.type(text)` → `keyboard.press("Enter")` | click only if coords set; type only if text; **Enter always pressed** |
| `SCROLL` | `page.mouse.wheel(dx, dy)` | delta from direction (`UP`=(0,-600), etc.) |
| `GO_BACK` / `REFRESH` | `page.go_back()` / `page.reload()` | |
| `GOTO` | `page.goto(url)` | only if url set |
| `WAIT` | `asyncio.sleep(min(max(secs,0),10))` | default 2.0 s |
| `RESTART` | `goto(url)` if set else `reload()` | runner normally rewrites RESTART→GOTO(start) |
| `ANSWER` / unknown | no-op | ANSWER handled by the loop; unknown never crashes |

Gotchas: missing coords silently skip; WRITE always submits (Enter); unrecognized actions fall through quietly.

---

## 4. `detect.py` — success & stuck detection

`SuccessPredicate = Callable[[page], bool | Awaitable[bool]]`. `is_success(page, predicate)` awaits the predicate if needed, returns `bool`, and returns `False` on **any exception** (never a false positive).

**Critical default:** `_DEFAULT_SUCCESS_SELECTORS = ()` is **empty** — generic markers like "Welcome"/"Success" false-positive on real sites. So **without a caller-supplied predicate, the only path to `SUCCESS` is the persona emitting an `answer()` action.** Callers who know a page's success signal must pass an explicit predicate (e.g. `#ok` visibility for `hostile_form.html`).

`is_stuck(history, window=3)` → `True` when the last 3 captions are byte-for-byte identical and non-empty. Gotcha (pre-fix): tremor jitter perturbs click coords → different captions → repeated dead-button clicks *escape* this exact-string check. The `debug` fix hardens it.

---

## 5. `thumbnail.py`

`to_thumb_data_uri(png_bytes, max_w=320, quality=60) -> str` — flattens alpha to RGB, downscales to ≤320px wide (LANCZOS), encodes JPEG q60, returns a `data:image/jpeg;base64,…` URI. Empty input or any exception → `""` (a bad frame never kills the loop). Never upscales.

---

## 6. `testing.py` — test doubles

- `CollectingEventSink` — an `EventSink` that appends every event to `.events`; `of_type(cls)` filters by type.
- `StubPersonaAgent` — a `PersonaAgent` replaying a fixed script; once exhausted it returns `Action(type=ANSWER, ...)` so a short script self-terminates as SUCCESS rather than wedging.

---

## 7. The simulated-clock patience fix (commit `416e488`, branch `debug` — NOT in `main`)

**The bug:** `deadline_s` was enforced as real wall-clock around the whole loop. With a shared 5-RPM Holo limiter, each `decide()` queued 20–90 s of infra latency, charged against every persona's patience → ~90% of runs died `time_budget` regardless of the target page's usability.

**The fix (`session.py`):** the runner now charges a **simulated persona clock**:
- New constants `_THINK_TIME_S = 4.0`, `_SETTLE_MS = 500`, `_SETTLE_LOAD_TIMEOUT_MS = 5000`, `_WALL_CAP_S = 7200`.
- `state["sim_s"]` tracks persona-experienced seconds. `agent.decide()` is wall-timed only to record `latency_ms` — **excluded from `sim_s`**.
- After actuating: `await _settle(page)` (`domcontentloaded` + 500 ms), then `state["sim_s"] += _THINK_TIME_S + (time.monotonic() - exec_t0)` — i.e. **4 s think-time + real page/actuation time**, nothing else.
- In-loop check `if sim_s >= persona.deadline_s: outcome = TIME_BUDGET; return`.
- The outer `wait_for` becomes a `_WALL_CAP_S = 7200` s anti-hang guard mapping to **`ERROR`**, never `TIME_BUDGET`.
- `duration_s` reports `state["sim_s"]` (persona-experienced time).
- Success **re-checked after** the action executes, so completing on the final step counts.
- **Screen-change annotation:** each step diffs the screenshot vs the previous (`frames_similar`); if unchanged, appends `NO_CHANGE_NOTE` to the last history entry.

**`detect.py` additions:** `NO_CHANGE_NOTE`; `frames_similar(a, b, threshold=1.5)` (mean-abs-diff on 96px grayscale thumbs, `False` on decode error); `is_stuck` gains `click_radius_px=14` — catches `window` clicks within 14 px of each other when the later ones carry `NO_CHANGE_NOTE` (tremor-jittered dead-spot hammering the string check missed). `testing.py`: `StubPersonaAgent` gains `decide_delay_s` to prove slow latency does *not* burn the deadline.

**Verified live:** power-user + tremor vs `hostile_form` finished in **54 simulated seconds** with **zero `time_budget` deaths** while individual Holo calls took up to 77 s wall-clock.

---

## 8. Cross-cutting gotchas

- Coords are never rescaled anywhere; the engine already produced true viewport pixels.
- Video only flushes on `context.close()` — must close before `video.save_as`.
- Success without a predicate is answer-only on `main`.
- `task` arg is unused by the runner — it's baked into the agent's prompt upstream.
- WRITE always presses Enter.
- Thumbnail (`""`) and predicate (`False`) failures are swallowed so a bad frame never crashes the loop.
