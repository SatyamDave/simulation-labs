# Frozen Contracts Reference — `shared/ghostpanel_contracts/contracts.py`

> **FROZEN — must not be edited.** All cross-module communication goes through these Pydantic v2 models. They are the reason five parallel agents can build on five branches and merge with zero conflicts: every module codes against these types, never against another module's source.

Everything is JSON-serializable; **bytes never go on the wire** (screenshots travel as base64 in `thumbnail_b64`). `CONTRACT_VERSION = "1.0.0"` is bumped only via the orchestrator; modules assert against it to detect a stale checkout. Nearly every model sets `model_config = ConfigDict(extra="forbid")`, so an unknown field is rejected at validation — a deliberate guard across branches.

---

## Enums

| Enum | Members | Role |
|---|---|---|
| `PerturbationKind` | `blur`, `downscale`, `cvd`, `tremor`, `small_viewport`, `impatience`, `low_literacy` | Which perception/actuation channels are degraded (UI/analytics tags). |
| `CVDType` | `protan`, `deutan`, `tritan` | Colour-vision-deficiency variant → DaltonLens `Deficiency`. |
| `ActionType` | `click`, `write`, `scroll`, `go_back`, `refresh`, `wait`, `goto`, `restart`, `answer` | The Holo navigation action space; the discriminator the runner executes on. |
| `ScrollDirection` | `up`, `down`, `left`, `right` | Direction carried by a `SCROLL` action. |
| `PersonaOutcome` | `success`, `step_budget`, `time_budget`, `stuck`, `error` | How a session ended. **Only `success` counts as completion; `error` is infra failure, excluded from survival stats.** |
| `EventType` | `run_started`, `persona_started`, `step`, `persona_finished`, `run_finished` | Tag values for the WebSocket discriminated union. |

---

## Data models

**`Viewport`** — `width: int = 1280`, `height: int = 800`. The pixel canvas; the coordinate space all `x/y` are expressed in.

**`PersonaConfig`** — a synthetic user (persona physics are **mechanical, not roleplayed**). Validates `personas/*.json`. Fields: `id`, `name`, `blurb`, `voice_id?`, `viewport`, `language="en"`; **perception** perturbations (applied before Holo sees the frame): `blur_sigma=0.0`, `downscale_factor=1.0`, `cvd_type?`, `cvd_severity=0.0`; **actuation** perturbation (applied after Holo decides): `tremor_sigma_px=0.0`; **patience/cognition**: `max_steps=30`, `deadline_s=120.0` (the simulated patience clock), `literacy_note=""`; and `active_perturbations: list[PerturbationKind]` (UI/analytics only).

**`Observation`** — a single frame handed to a `PersonaAgent`. Uniquely sets `arbitrary_types_allowed=True` to hold raw bytes. Fields: `raw_png: bytes` (**un-perturbed** — the engine perturbs a copy), `viewport`, `step_index`, `url`.

**`Action`** — a decoded Holo action, **already de-perturbed into TRUE viewport pixels** (the runner executes it verbatim, never re-scales). Fields: `type: ActionType`, `x?/y?` (viewport px), `text?` (WRITE/ANSWER), `direction?`, `url?` (GOTO), `seconds?` (WAIT), `caption` (shown on the UI tile), `raw` (verbatim model output, for debugging).

**`StepRecord`** — one executed step: `persona_id`, `step`, `action`, `thumbnail_b64`, `latency_ms` (Holo round-trip), `note`.

**`PersonaResult`** — the full outcome of one session (runner → report/voice boundary): `persona_id`, `outcome`, `steps: list[StepRecord]`, `failure_coords?` (the abandonment pixel), `failure_step?`, `failure_reason`, `duration_s`, `video_path?` (`.webm`), `transcript` + `audio_path?` (filled by Agent 5).

**`HeatPoint`** — `x`, `y`, `weight=1.0`, `persona_id`. One abandonment-heatmap point.

**`SurvivalPoint`** — `persona_id`, `persona_name`, `outcome`, `steps_survived`, `completed: bool`.

**`RunReport`** — the aggregate deliverable: `run_id`, `target_url`, `task`, `contract_version`, `results`, `survival`, `heatmap_points`, `completion_rate`, `generated_at` (ISO8601).

---

## Event wire models — the `RunEvent` discriminated union

These are **the exact JSON pushed over the WebSocket**. Agent 3 emits them; Agent 4 renders them. Every event carries an `event:` field typed `Literal[EventType.X]` **with a default value**, so the tag auto-populates on construction and is the first key on the wire.

| Model | `event` | Fields |
|---|---|---|
| `RunStarted` | `run_started` | `run_id`, `target_url`, `task`, `personas: list[PersonaConfig]` — fired once at launch. |
| `PersonaStarted` | `persona_started` | `run_id`, `persona_id` — a session began. |
| `StepEvent` | `step` | `run_id`, `persona_id`, `step`, `caption`, `thumbnail_b64`, `x?`, `y?` — emitted on **every** step to keep the grid alive. |
| `PersonaFinished` | `persona_finished` | `run_id`, `persona_id`, `outcome`, `failure_coords?`, `failure_reason`, `steps_survived`. |
| `RunFinished` | `run_finished` | `run_id`, `report_url`, `completion_rate` — the terminal event; the WS route closes on it. |

```python
RunEvent = Annotated[
    Union[RunStarted, PersonaStarted, StepEvent, PersonaFinished, RunFinished],
    Field(discriminator="event"),
]
```

**Why discriminated-on-`event`:** Pydantic reads the `event` string first and routes to the one matching model — O(1), no trial-and-error, with a precise error on an unknown tag. Because each subtype pins `event` to a distinct `Literal`, dumping any member yields JSON like `{"event":"step", …}` and loading that JSON reconstructs the correct type. That 1:1 correspondence is exactly why "`RunEvent` is the exact JSON on the WebSocket": the server dumps a model to JSON, pushes the string, and the TypeScript client `switch`es on `event` with no schema negotiation — a self-describing, forward-compatible envelope for a live heterogeneous stream over one channel.

---

## Protocols (interfaces)

All are `@runtime_checkable`, so `isinstance(obj, Proto)` works (each agent's definition-of-done check). Concrete class names and module paths are fixed so the composition root can import and wire them.

| Protocol | Concrete impl | Method(s) |
|---|---|---|
| `HoloClient` | `engine.holo_client.LiveHoloClient` / `FakeHoloClient` | `async localize(image_png, instruction) -> (x,y)`; `async navigate(image_png, task, history) -> Action` |
| `PersonaAgent` | `engine.persona_agent.HoloPersonaAgent` | attr `persona`; `async decide(obs, history) -> Action` |
| `EventSink` | `server.events.WebSocketEventSink` / `runner.testing.CollectingEventSink` | `async emit(event: BaseModel) -> None` — safe from many concurrent tasks |
| `SessionRunner` | `runner.session.PlaywrightSessionRunner` | `async run(persona, agent, target_url, task, sink, run_id) -> PersonaResult` |
| `VoiceEngine` | `voice.gradium_voice.GradiumVoiceEngine` | `async exit_interview(result, persona) -> str`; `async mutter(text, voice_id) -> str` |
| `ReportBuilder` | `report.builder.SurvivalReportBuilder` | `build(run_id, target_url, task, results, personas) -> RunReport` (sync) |
