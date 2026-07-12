# Engine Module — `src/ghostpanel/engine/`

> **Owner:** Agent 1 (`agent/engine`) · **Branch registry classes:** `LiveHoloClient`, `FakeHoloClient`, `HoloPersonaAgent`, `load_personas`

The engine owns the perception-to-actuation loop for a single synthetic user ("persona"). It degrades a screenshot to simulate a human impairment, asks the hosted **Holo Models** vision-language model what to do next, parses the reply into a strongly-typed `Action`, and de-perturbs (jitters + clamps) the click coordinates back into **true viewport pixels**. The runner (Agent 2) executes the returned `Action` verbatim without ever re-scaling.

All shared types (`Action`, `PersonaConfig`, `Observation`, `HoloClient`, …) are frozen in `shared/ghostpanel_contracts/contracts.py` and must not be edited by the engine.

---

## 1. Data flow

```
Observation.raw_png  (Playwright PNG, TRUE pixels — un-perturbed)
   │
   ▼  HoloPersonaAgent.decide()
   │
 [1] perceive(raw_png, persona)              # perturbation.py — degrade a COPY, dims unchanged
   │      downscale → blur → CVD
   ▼  degraded PNG (same W×H)
   │
 [2] holo.navigate(degraded, task, history)  # holo_client.py
   │      _data_uri() → OpenAI chat.completions → text
   │      parse_action(text, w, h, normalize=?)   # JSON → Click(x,y) → keyword → center
   │      LIVE denormalizes 0–1000 → pixels; FAKE passes pixels through
   ▼  Action (coords in image/viewport pixels)
   │
 [3] actuate(action, persona, w, h)          # perturbation.py — tremor jitter + clamp
   ▼
 Action in TRUE viewport pixels  ──►  runner executes it verbatim
```

The engine perturbs a **copy**; `Observation.raw_png` is the un-perturbed screenshot. Because every image transform preserves dimensions (the "golden rule"), returned coordinates never need a smart-resize remap — the only coordinate transforms are **denormalization** (0–1000 → px, live only) and **tremor jitter**.

---

## 2. `holo_client.py`

The module docstring states the coordinate contract explicitly: the hosted **Holo 3.1** API returns coordinates normalized to a **0–1000 grid**, confirmed empirically — a true-centre click at (547,430) in a 1280×800 screenshot came back as `Click(426,536)`, and `426/1000*1280 = 545`, `536/1000*800 = 429`. Therefore **the live client ALWAYS denormalizes**; **`FakeHoloClient` returns pixel coords directly and does NOT denormalize.** This asymmetry is the single most important fact in the module.

### 2.1 `RateLimiter` — shared asyncio token bucket (`holo_client.py:32-65`)

```python
def __init__(self, rpm: float = 10.0) -> None:
    self.rpm = float(rpm) if rpm and rpm > 0 else 10.0
    self._capacity = max(1.0, self.rpm)
    self._tokens = self._capacity
    self._rate = self.rpm / 60.0          # tokens per second
    self._updated = time.monotonic()
    self._lock = asyncio.Lock()
```

- Token bucket sized by **requests-per-minute**; refills continuously at `rpm/60` tokens/sec up to a burst capacity of `rpm`. Holo free tier = **10 RPM**.
- **One instance is shared across every persona's client** so the whole swarm respects a single budget.
- `_refill()` adds `elapsed * _rate` tokens (capped at `_capacity`). `acquire()` loops under the lock; if `_tokens >= 1.0` consumes one and returns, else sleeps `min(max(wait_s, 0.01), 60.0)` **outside** the lock and retries.
- Gotcha: non-positive `rpm` silently coerces to 10.0.

### 2.2 Parsing (`parse_action`, `parse_click`, `_action_from_dict`)

`parse_action(text, w, h, normalize=False) -> Action` is the central parser. Precedence:

1. **JSON object** anywhere in the text (`_JSON_OBJ_RE`, `json.loads`) → `_action_from_dict`.
2. **Malformed-JSON click salvage** (`holo_client.py:171-184`) — the key live-model edge case: the model sometimes emits `{"action": "click", "x": 426, 536}`, dropping the `"y"` key, which defeats both `json.loads` and `Click(x,y)`. If the blob matches `"action":"(left_)?(click|tap)"`, it grabs the **first two numbers** as `(x, y)` and denormalizes/clamps.
3. **`Click(x, y)` short form** via `parse_click`.
4. **Keyword fallbacks**: `scroll <dir>`, `go_back`, `refresh`.
5. **Give up → center click** `Action(type=CLICK, x=w//2, y=h//2, text="unparsed")` so the runner still makes progress.

`_action_from_dict` maps many action-name spellings via `_ACTION_ALIASES` (`click`/`tap`→CLICK, `write`/`type`/`fill`→WRITE, `goto`/`navigate`→GOTO, `answer`/`done`/`finish`→ANSWER, …), pulls coords from `x`/`y` or nested `coordinate`/`coordinates`/`position`, and text/url/seconds/direction from several key aliases. Coords are denormalized/clamped **only when both present**; missing CLICK/WRITE coords center in pixel space (never denormalized).

Helpers: `_to_int`, `_clamp(x,y,w,h)` → `[0,w-1]×[0,h-1]`, `_denormalize(x,y,w,h)` → `_clamp(round(x/1000*w), round(y/1000*h))` (**real model output only**), `_caption_for(...)` (human UI caption), `_data_uri(png)` → base64 `data:image/png;base64,…`, `_png_size(png)` reads width/height from the PNG **IHDR chunk** to avoid a Pillow import (falls back to Pillow for non-plain PNGs).

### 2.3 `LiveHoloClient` (`holo_client.py:299-395`)

`__init__(api_key, base_url, model, rpm=10.0, limiter=None, max_retries=4)` — lazily imports `openai.AsyncOpenAI`; uses a passed `limiter` (to share one across personas) or a fresh `RateLimiter(rpm)`.

`shared(cls, api_key, base_url, model, rpm=10.0) -> (LiveHoloClient, RateLimiter)` — convenience classmethod that builds a limiter, constructs the client with it, and **returns both** so callers can thread the same limiter into every persona.

`_chat(image_png, prompt)` — builds an OpenAI-compatible multimodal message (`{"type":"text"}` + `{"type":"image_url","image_url":{"url":data_uri}}`), retries `max_retries` times, calls `limiter.acquire()` **before each attempt**, then `chat.completions.create(model, messages, temperature=0.0)`. 429/rate errors → exponential backoff `min(2**attempt, 30)`; transient network → `min(2**attempt, 10)`; else re-raise. A rate-limiter token is consumed per attempt (retries included).

`localize(image_png, instruction) -> (int,int)` — localizer prompt → chat → `parse_click`, denormalized → **true pixels**.

`navigate(image_png, task, history) -> Action` — reads size, builds a **persona-free** nav prompt (`navigation_prompt(task, history, PersonaConfig(id="_", name="_"))`), chats, returns `parse_action(text, w, h, normalize=True)`. Because the `HoloClient.navigate` contract has no persona argument, the persona agent injects literacy/language notes by prepending them to the **task string** upstream.

### 2.4 `FakeHoloClient` (`holo_client.py:410-468`)

Deterministic, network-free stand-in used by runner, server, and tests so the swarm runs offline. `__init__(scripted_actions=None)`. Scripted items may be an `Action` (returned as-is), an `(x,y)` tuple (→ CLICK), or a `dict` (→ `_action_from_dict`, **default `normalize=False`** so scripted pixel coords pass through). Empty queue → deterministic center click. `navigate` **consumes** one queued item FIFO; `localize` peeks without consuming.

---

## 3. `persona_agent.py` — `HoloPersonaAgent`

Registry signature `(persona, holo)`; the real constructor is `__init__(persona, holo, task="")`.

`_effective_task(history) -> str` folds persona cognition into the task text (which survives the persona-free `navigate()` signature):
1. If `self.task` is empty, `history` non-empty, and `history[0]` starts with `"task:"`, use the text after the colon.
2. Append `persona.literacy_note` if set.
3. If `persona.language` is set and `!= "en"`, append *"You read more comfortably in '<lang>' than English."*

`decide(obs, history) -> Action`:
```python
degraded = perceive(obs.raw_png, self.persona)            # 1. same dims out
task     = self._effective_task(history)
raw      = await self.holo.navigate(degraded, task, history)  # 2. coords in image/viewport px
final    = actuate(raw, self.persona, obs.viewport.width, obs.viewport.height)  # 3. jitter + clamp
return final
```

Impairment is entirely mechanical: perception via `perceive`, cognition via task-text folding, actuation via `actuate`. **Impatience (`max_steps`/`deadline_s`) and viewport size are NOT enforced here** — they belong to the runner.

---

## 4. `perturbation.py`

**Golden rule:** every image transform returns an image whose `.size` equals the input's. All functions are deterministic and unit-testable; no network.

| Function | Effect | Notes |
|---|---|---|
| `blur(img, sigma)` | Gaussian blur (low acuity) | `sigma<=0` → no-op copy |
| `downscale_in_place(img, factor)` | resize down then back up (destroys high-freq detail) | `factor>=1 or <=0` → copy; `max(1,…)` guards zero-size |
| `apply_cvd(img, cvd_type, severity)` | colour-vision deficiency via `daltonlens` Machado-2009 matrices | `severity<=0`/`None` → copy; severity 0..1 |
| `jitter_coords(x, y, sigma_px, w, h, rng=None)` | add `N(0, sigma_px)` to x,y, clamp in-bounds | motor tremor; `sigma<=0` → identity |

Pipelines:
- `perceive(png_bytes, persona) -> bytes` — opens PNG, converts to RGB, applies **downscale → blur → CVD** (each gated on the persona field), then `assert img.size == original_size` — a hard runtime guard. Output is always RGB PNG (drops alpha).
- `actuate(action, persona, w, h, rng=None) -> Action` — if `action.x/.y` is `None`, returns unchanged; else jitters by `persona.tremor_sigma_px` and clamps to the viewport, returning `action.model_copy(update={"x":cx,"y":cy})`.

---

## 5. `personas.py` + persona JSON schema

`load_personas(ids=None) -> list[PersonaConfig]` globs `personas/*.json`, validates each via `PersonaConfig.model_validate`, raises on duplicate id. With `ids`: returns matching personas **in `ids` order**, silently skipping unknowns. Without: all personas **sorted by id**. `PersonaConfig` uses `extra="forbid"`, so a typo'd JSON key raises.

### Persona schema (`PersonaConfig`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `id` / `name` | str | — | slug / display name (required) |
| `blurb` | str | `""` | one-line UI description |
| `voice_id` | str? | `None` | Gradium voice |
| `viewport` | `{width,height}` | 1280×800 | render size |
| `language` | str | `"en"` | prompt / interview language |
| `blur_sigma` | float | `0.0` | blur radius px |
| `downscale_factor` | float | `1.0` | resize factor (0.5 = half) |
| `cvd_type` / `cvd_severity` | enum? / float | `None` / `0.0` | protan/deutan/tritan, 0..1 |
| `tremor_sigma_px` | float | `0.0` | coord noise sigma |
| `max_steps` | int | `30` | impatience (runner-enforced) |
| `deadline_s` | float | `120.0` | patience budget (runner-enforced) |
| `literacy_note` | str | `""` | appended to nav prompt |
| `active_perturbations` | list | `[]` | UI/analytics tags only |

### The 8 shipped personas

| id | name | viewport | blur_σ | downscale | cvd | tremor_px | max_steps | deadline_s | lang |
|---|---|---|---|---|---|---|---|---|---|
| `ai-agent` | Agent (headless AI) | default | 0 | 1.0 | — | 0 | 40 | 240 | en |
| `colorblind` | Jordan (deuteranopia) | default | 0 | 1.0 | deutan@0.9 | 0 | 30 | 120 | en |
| `grandma-72` | Margaret, 72 | default | 1.2 | 1.0 | — | 4.0 | 12 | 90 | en |
| `impatient-mobile` | Priya (impatient) | **390×844** | 0 | 1.0 | — | 6.0 | 8 | 30 | en |
| `low-vision` | Sam (low vision) | default | 3.5 | 0.4 | — | 0 | 25 | 150 | en |
| `non-native` | Luca (non-native EN) | default | 0 | 1.0 | — | 0 | 20 | 100 | **it** |
| `power-user` | Alex (power user) | default | 0 | 1.0 | — | 0 | 40 | 240 | en |
| `tremor` | Dev (hand tremor) | default | 0 | 1.0 | — | **14.0** | 30 | 150 | en |

`ai-agent` and `power-user` are zero-impairment controls. `impatient-mobile` is the only viewport override; `non-native` is the only non-English persona. `active_perturbations` is purely descriptive — behaviour comes from the numeric fields.

---

## 6. `prompts.py`

- **Localizer** (verbatim from the hai-cookbook): *"Localize an element on the GUI image according to my instructions and output a click position as Click(x, y) with x num pixels from the left edge and y num pixels from the top edge."*
- **Navigation** — `navigation_prompt(task, history, persona)` assembles the `_ACTION_SPACE` block (click/write/scroll/go_back/refresh/wait/goto/restart/answer, "prefer a JSON object", dismiss-modals/make-progress/don't-repeat guidelines) + `Task:` + the last 10 history lines + literacy/language notes.

---

## 7. Consolidated gotchas

1. **Live always denormalizes (0–1000 → px); Fake never does.** Mixing these up mis-scales every click.
2. **Missing-`y`-key salvage** — the live model emits `{"action":"click","x":426, 536}`; a dedicated regex path recovers it.
3. **Center-click fallbacks are always pixel-space**, never denormalized.
4. **Rate-limiter token consumed per attempt**, retries included.
5. **`perceive` forces RGB** (drops alpha) and asserts dimension invariance.
6. **Perturbation order is fixed:** downscale → blur → CVD.
7. **Engine does not enforce `max_steps`/`deadline_s`/viewport size** — the runner does; `decide` only uses `obs.viewport` for jitter/clamp.
8. **`temperature=0.0`** on every live call for determinism.
