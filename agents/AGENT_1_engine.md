# AGENT 1 — Engine (Holo client + Persona agent + Perturbations)

**Branch:** `agent/engine`   **You own:** `src/ghostpanel/engine/**`, `personas/**`,
`tests/engine/**`   **Never edit:** `shared/**`, `pyproject.toml`, other modules.

You are the **foundation**. Everyone consumes your `Action` output and your `PersonaAgent`.
Read `CLAUDE.md` (architecture, class registry, Holo facts) and
`shared/ghostpanel_contracts/contracts.py` first. Do **not** read other modules' source.

## Mission

Turn a raw screenshot + a persona into the next `Action`, having **mechanically degraded**
perception and actuation to model that persona's impairment. You wrap the H Company Holo
Models API and you own the "physics" of every persona.

## Files to create

```
src/ghostpanel/engine/
  holo_client.py     # LiveHoloClient (real Holo), FakeHoloClient (scripted, for everyone's tests)
  perturbation.py    # pure image/coord transforms (blur, downscale-in-place, CVD, jitter)
  persona_agent.py   # HoloPersonaAgent: perturb → Holo → parse → jitter
  personas.py        # load_personas(ids=None) -> list[PersonaConfig]  (reads personas/*.json)
  prompts.py         # localization + navigation prompt builders (+ literacy modifier)
tests/engine/
  test_perturbation.py
  test_persona_agent.py
  test_personas.py
personas/
  *.json             # 6–8 persona configs (see list below)
```

## Contracts you implement (from `ghostpanel_contracts`)

- `HoloClient` → `LiveHoloClient(api_key, base_url, model, rpm)` and `FakeHoloClient(scripted_actions=None)`
- `PersonaAgent` → `HoloPersonaAgent(persona: PersonaConfig, holo: HoloClient)`
- `load_personas(ids: list[str] | None) -> list[PersonaConfig]`

`isinstance(LiveHoloClient(...), HoloClient)` and `isinstance(HoloPersonaAgent(...), PersonaAgent)`
must be `True` (Protocols are `@runtime_checkable`).

## Tasks

### 1. `holo_client.py`
- **`LiveHoloClient`** using the OpenAI SDK:
  ```python
  from openai import AsyncOpenAI
  self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
  ```
  - `localize(image_png, instruction) -> (x, y)`: send the image as a base64 **data URI** in an
    `image_url` content part + the localization prompt (`prompts.py`). Parse `Click(x, y)` from
    the response. Return ints.
  - `navigate(image_png, task, history) -> Action`: send image + navigation prompt (with action
    schema + `history` of prior captions). Parse the model's chosen action into an `Action`
    (`ActionType` + fields + a human `caption` + `raw`).
  - **Shared rate limiter:** an `asyncio` token bucket sized by `rpm` (default from `HAI_RPM`,
    free tier = 10). A *single* limiter instance must be shareable across all personas — expose
    it so the swarm uses one budget (e.g. accept an optional `limiter` arg, or a classmethod
    `LiveHoloClient.shared(...)`). Retry on 429 with backoff.
  - **smart_resize:** if you keep the image at its native dimensions you need **no** coordinate
    remap. If Holo returns normalized 0–1000 coords (older behavior), detect and rescale to the
    real image size. Document which you observed. **Never** change image dims silently.
- **`FakeHoloClient(scripted_actions=None)`**: returns queued `Action`s (or a deterministic
  default like "click center") so Agents 2/3 and your own tests run with **no network**. This is
  in the class registry — other agents import it. Keep it dependency-free and stable.

### 2. `perturbation.py` (pure functions, no Holo, fully unit-testable)
Operate on `PIL.Image` / numpy; **keep output dimensions equal to input** (golden rule):
- `blur(img, sigma)` → `img.filter(ImageFilter.GaussianBlur(sigma))`
- `downscale_in_place(img, factor)` → resize to `(w*factor, h*factor)` then back to `(w, h)`
- `apply_cvd(img, cvd_type, severity)` → DaltonLens `Simulator_Machado2009().simulate_cvd(arr,
  Deficiency.{PROTAN|DEUTAN|TRITAN}, severity)`
- `jitter_coords(x, y, sigma_px, w, h)` → numpy gaussian noise, clamp to `[0,w) × [0,h)`
- `perceive(png_bytes, persona) -> png_bytes` → apply the persona's enabled perception
  perturbations in order, return PNG bytes (same dims).
- `actuate(action, persona, w, h) -> Action` → if the action has coords and persona has
  `tremor_sigma_px > 0`, jitter them; return a new `Action`.

### 3. `prompts.py`
- `localization_prompt(instruction)` — the exact cookbook localizer wording (see CLAUDE.md).
- `navigation_prompt(task, history, persona)` — instruct the model to pick from the action
  space and return structured output; **append `persona.literacy_note`** when set (e.g. "Read
  the screen literally. Do not assume an icon is a menu. Do not guess conventions.").

### 4. `persona_agent.py`
`HoloPersonaAgent.decide(obs: Observation, history) -> Action`:
1. `perceive(obs.raw_png, self.persona)` → degraded PNG (same dims).
2. `self.holo.navigate(degraded_png, task_from_history_or_context, history)` → raw `Action`.
   (Task text: the agent is constructed per-persona; the task string is passed via `history`
   convention or store it on the agent — keep it simple, document your choice.)
3. `actuate(action, self.persona, obs.viewport.width, obs.viewport.height)` → jittered `Action`.
4. Return the final `Action` in **true viewport pixels**.

### 5. `personas.py` + `personas/*.json`
`load_personas(ids)` reads `personas/*.json`, validates each with `PersonaConfig.model_validate`,
returns the list (filtered by `ids` if given). Ship these personas (tune numbers to taste):

| id | name | key perturbations |
|----|------|-------------------|
| `grandma-72` | Margaret, 72 | `low_literacy` (literal reading), small `max_steps`, mild blur |
| `low-vision` | Sam (low vision) | `blur` (high sigma) + `downscale` |
| `colorblind` | Jordan (deuteranopia) | `cvd` deutan severity ~0.9 |
| `tremor` | Dev (hand tremor) | `tremor` sigma ~14px |
| `impatient-mobile` | Priya (impatient, mobile) | `small_viewport` (390×844) + short `deadline_s` |
| `non-native` | Luca (non-native EN) | `language`≠en literacy note, mild patience limit |
| `power-user` | Alex (baseline) | none — the control |
| `ai-agent` | Agent (headless AI) | none — "is your site agent-ready?" |

## Verification (must pass before merge)

```bash
pytest tests/engine/ tests/test_contracts.py -q
```
- `test_perturbation.py`: load `fixtures/sample_screenshot.png`; assert each perturbation
  **changes pixels** but **preserves `img.size`**; assert `jitter_coords` stays in-bounds and
  has ~expected spread; CVD reduces red/green separation.
- `test_persona_agent.py`: with `FakeHoloClient`, assert `decide()` returns an `Action` with
  in-viewport coords and that a `tremor` persona's coords differ from the fake's raw coords.
- `test_personas.py`: `load_personas()` returns ≥6 valid `PersonaConfig`; ids unique.
- `isinstance` checks against `HoloClient` / `PersonaAgent` pass.
- **Live smoke (manual, needs `HAI_API_KEY`):** one `LiveHoloClient.localize()` on the sample
  screenshot returns plausible coords. Put this behind `@pytest.mark.skipif(no key)`.

## Done when
Registry classes exist at the exact paths, Protocols satisfied, tests green, only your paths
touched. Hand off: Agents 2 & 3 will import `FakeHoloClient`, `HoloPersonaAgent`,
`LiveHoloClient`, `load_personas`.
