# AGENT 5 — Voice + Reporting

**Branch:** `agent/voice-report`   **You own:** `src/ghostpanel/voice/**`,
`src/ghostpanel/report/**`, `tests/voice/**`, `tests/report/**`
**Never edit:** `shared/**`, `pyproject.toml`, other modules.

You turn cold action-traces into two things judges remember: **numbers** (survival curve +
abandonment heatmap) and **empathy** (each dead persona explaining, in its own cloned voice, why
it quit). You depend only on the contracts — build fully in parallel. Read `CLAUDE.md` (Gradium
facts) and the contracts first.

## Files to create

```
src/ghostpanel/voice/
  gradium_voice.py   # GradiumVoiceEngine (implements VoiceEngine)
  narrate.py         # action-trace → first-person exit-interview TEXT (Claude, with template fallback)
  voices.py          # assign/clone a distinct Gradium voice_id per persona
src/ghostpanel/report/
  builder.py         # SurvivalReportBuilder (implements ReportBuilder)
  heatmap.py         # aggregate failure coords → HeatPoint[]
  html_report.py     # RunReport → standalone HTML artifact (Jinja2)
tests/voice/
  test_narrate.py  test_gradium_voice.py
tests/report/
  test_builder.py  test_heatmap.py
```

## Contracts you implement / consume

- **Implement (registry):**
  - `voice.gradium_voice.GradiumVoiceEngine(api_key, artifact_dir, anthropic_key=None)` → `VoiceEngine`
  - `report.builder.SurvivalReportBuilder()` → `ReportBuilder`
- **Consume:** `PersonaResult`, `PersonaConfig`, `PersonaOutcome`, `RunReport`, `SurvivalPoint`,
  `HeatPoint`, `StepRecord`.

## Reporting tasks

### 1. `builder.py` — `SurvivalReportBuilder.build(run_id, target_url, task, results, personas)`
- Build one `SurvivalPoint` per result: `persona_name` (look up from `personas`), `outcome`,
  `steps_survived = len(result.steps)` (or `failure_step`), `completed = outcome == SUCCESS`.
- `completion_rate = successes / (non-error personas)` — **exclude `ERROR`** (infra ≠ human give-up).
- `heatmap_points` via `heatmap.py`.
- Stamp `contract_version` and `generated_at` (ISO8601). Return a valid `RunReport`.

### 2. `heatmap.py`
`build_heatmap(results) -> list[HeatPoint]`: take each non-success `failure_coords`, emit a
`HeatPoint(x, y, weight, persona_id)`. Optionally cluster nearby points and sum weights. Clamp to
viewport bounds. (The frontend renders the blobs; you just supply weighted points.)

### 3. `html_report.py`
`render_html(report: RunReport) -> str` (Jinja2): a standalone, self-contained page — headline
completion rate, a survival table, an inline-SVG survival bar chart, the heatmap points listed,
links to `.webm`/`.wav` artifacts, and each exit-interview transcript. This is the leave-behind a
PM/VC keeps. Write it to `<artifact_dir>/<run_id>/report.html`.

## Voice tasks

### 4. `voices.py`
`assign_voices(personas, client) -> dict[persona_id, voice_id]`. Prefer **distinct preset Gradium
voices** for reliability; optionally **clone** from a short sample via
`gradium.voices.create(client, audio_file=..., name=...)` (~10s). If a persona already has
`voice_id` set in its config, respect it. Make the grandmother sound old, the impatient one clipped,
etc., as far as available voices allow.

### 5. `narrate.py` — `async def write_exit_interview(result, persona, anthropic_key=None) -> str`
Turn the **real action trace** into a short first-person explanation grounded in what actually
happened — never generic. Feed Claude (`anthropic` SDK, model from `ANTHROPIC_MODEL`) the persona,
the ordered `caption`s, the `outcome`, and `failure_reason`; ask for 1–3 sentences in the persona's
voice and `persona.language`. Example target: *"I kept pressing the big blue button because that's
usually the one you press, but it just talked about plans. I never found where to actually make my
account."* Provide a **deterministic template fallback** when no `anthropic_key` (so tests + the
demo never hard-fail on a missing key).

### 6. `gradium_voice.py` — `GradiumVoiceEngine`
- `async exit_interview(result, persona) -> str`: `text = write_exit_interview(...)`; synthesize via
  Gradium TTS (`client.tts(setup={"voice_id": voice_for(persona), "output_format": "wav"},
  text=text)`); write `<artifact_dir>/<run_id?>/<persona_id>.wav`; set `result.transcript` and
  `result.audio_path`; return the wav path.
- `async mutter(text, voice_id) -> str`: short one-liner TTS for optional in-run "muttering."
- Auth: `GRADIUM_API_KEY` via the `gradium` SDK. Handle the SDK being unconfigured gracefully
  (raise a clear error only when actually called without a key; don't crash on import).
- (Optional, for the live demo) an STT helper using `client.stt_realtime(...)` so a judge can ask
  "why did you quit?" and get a spoken answer — semantic VAD rides in the STT stream.

## Verification (must pass before merge)

```bash
pytest tests/report/ tests/voice/ tests/test_contracts.py -q
```
- `test_builder.py`: feed the `PersonaResult`s from `fixtures/run.json`; assert `completion_rate`
  math is correct, one `SurvivalPoint` per persona, `ERROR` excluded, valid `RunReport`.
- `test_heatmap.py`: failure coords in → `HeatPoint`s within viewport bounds; success personas
  contribute none.
- `test_narrate.py`: template fallback (no key) produces text that **references the actual
  captions/outcome** (e.g. contains the decoy-button idea for the grandma fixture).
- `test_gradium_voice.py`: `isinstance(GradiumVoiceEngine(...), VoiceEngine)`; with no key, calling
  synth raises a clear error (don't hit the network in unit tests).
- **Live smoke (manual, needs `GRADIUM_API_KEY`):** one `exit_interview` produces a playable `.wav`;
  put behind `@pytest.mark.skipif(no key)`.

## Done when
Registry classes at exact paths, both Protocols satisfied, report math + narration grounded in real
traces, one real `.wav` proven manually, tests green (no keys needed for unit tests), only your
paths touched.
