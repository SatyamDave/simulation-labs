# Voice & Report Modules — `src/ghostpanel/voice/` + `src/ghostpanel/report/`

> **Owner:** Agent 5 (`agent/voice-report`) · **Registry classes:** `GradiumVoiceEngine`, `SurvivalReportBuilder`

These two modules consume the `PersonaResult` traces the runner produces and turn them into (a) a `RunReport` aggregate + a standalone offline HTML leave-behind, and (b) synthesized first-person exit-interview `.wav` files. A recurring design theme: **never hard-fail the demo** — every division is guarded and every LLM/voice call degrades gracefully.

---

## REPORT

### `report/builder.py` — `SurvivalReportBuilder`

The concrete `ReportBuilder`. Key business rule (module docstring): **`ERROR` outcomes are infra failures and are excluded from the completion-rate denominator.** Constructor takes no args.

`_steps_survived(result)` — "how far the persona got": prefers `result.failure_step`, falls back to `len(result.steps)` (no `+1`). A success with no failure_step and no steps → `0`.

`build(run_id, target_url, task, results, personas) -> RunReport`:
1. `name_by_id = {p.id: p.name for p in personas}`.
2. **Survival curve** — one `SurvivalPoint` per result (1:1, no filtering — even `ERROR` gets a row): `persona_name` from the lookup (`""` if absent), `steps_survived`, and `completed = (outcome == SUCCESS)` (**only exact SUCCESS**).
3. **Completion rate** — the load-bearing logic:
   ```python
   non_error = [r for r in results if r.outcome != PersonaOutcome.ERROR]
   successes = sum(1 for r in non_error if r.outcome == PersonaOutcome.SUCCESS)
   completion_rate = (successes / len(non_error)) if non_error else 0.0
   ```
   Errors dropped from both numerator and denominator; guarded division.
4. `heatmap_points = build_heatmap(results)`.
5. Assemble `RunReport` with `contract_version=CONTRACT_VERSION` and `generated_at = datetime.now(timezone.utc).isoformat()`.

**Gotcha:** `survival` (includes error rows) and the `completion_rate` denominator (excludes them) can disagree — e.g. 3 survival points but `completion_rate == 0.5` (1 success / 2 non-error).

### `report/heatmap.py` — `build_heatmap`

A **filter-and-clamp**, not a histogram. `DEFAULT_VIEWPORT = (1280, 800)`. For each result: **skip if `SUCCESS`** (a success never "abandoned"); **skip if `failure_coords is None`**; else clamp `(int(x), int(y))` into `[0,width-1]×[0,height-1]` and append `HeatPoint(x, y, weight=1.0, persona_id=...)`. Every point has flat `weight=1.0`; no aggregation (client-side binning does that). Verified clamps: `(99999,88888)→(1279,799)`, `(-40,-5)→(0,0)`.

### `report/html_report.py` — standalone offline HTML

Renders a `RunReport` into a fully self-contained HTML file (Jinja2 with `autoescape` on for html/xml — XSS-safe for untrusted trace text). Everything (CSS, the survival bar chart as **inline SVG**) is embedded so a PM/VC can open it offline.

Includes: header (task/URL/run id/`generated_at`/`contract_version`); a headline `{completion_pct}% … ({successes}/{non_error})`; a **survival** section with a per-persona inline-SVG bar chart (green `#1a9c4c` if completed else red `#c0392b`, `role="img"` + `aria-label`) and a table; an **abandonment heatmap** table (or "No abandonment points"); and **exit-interview cards** per result with the transcript, optional `failure_reason`, and **artifact links** (`▶ audio (.wav)` from `audio_path`, `🎬 video (.webm)` from `video_path`, relative so artifacts must be co-located).

`render_html(report)` recomputes `non_error`/`successes` from `results`, scales bars to ~400 px (`bar_unit = 400/max_steps`, double-guarded against empty/zero), and `completion_pct = round(completion_rate*100)`. `write_html_report(report, artifact_dir)` writes `<artifact_dir>/<run_id>/report.html` (UTF-8) and returns the path.

**Notes:** `html_report.py` is **untested** (no `tests/report/test_html_report.py` on `main`), and `render_html`/`write_html_report` are *not* part of the `ReportBuilder` protocol — they're standalone functions. Two independent `name_by_id` maps exist (builder derives from `personas`; renderer derives from `survival`).

---

## VOICE

### `voice/gradium_voice.py` — `GradiumVoiceEngine`

The concrete `VoiceEngine`. Verified Gradium SDK surface: `gradium.GradiumClient(api_key=...)`; `await client.tts(setup, text) -> TTSResult` where `setup` is like `{"voice_id": …, "output_format": "wav"}` and `TTSResult.raw_data` holds encoded bytes; `await client.stt(setup, audio_bytes) -> STTResult`.

`__init__(api_key, artifact_dir, anthropic_key=None)` — **construction is cheap and never touches the network**; `api_key` may be `None` (the error is deferred to first synth). `_get_client()` raises a clear `RuntimeError` (mentioning the API key) if `api_key` is falsy, else memoizes the client. `_tts_setup(voice_id)` always sets `output_format: "wav"` and adds `voice_id` only if truthy (else the Gradium default voice). `_write_wav(name, audio)` writes `<artifact_dir>/<name>.wav`.

`exit_interview(result, persona) -> str`:
1. `_get_client()` **first** — fail-fast before any mutation (no-key path leaves `result.audio_path` untouched).
2. `text = await write_exit_interview(result, persona, anthropic_key=self._anthropic_key)`.
3. `result.transcript = text` (mutates in place).
4. `tts = await client.tts(self._tts_setup(persona.voice_id), text)`.
5. `result.audio_path = self._write_wav(persona.id, tts.raw_data)`; returns the path.

`mutter(text, voice_id) -> str` — short in-run synth; builds a filesystem-safe slug (`mutter-<slug>.wav`). `transcribe(audio_wav) -> str` — optional live-demo STT helper (not part of the protocol).

**WAV header handling:** there is **none** on `main` — the engine trusts Gradium's `output_format:"wav"` to return a valid RIFF container and writes `raw_data` verbatim. (The `repeated-bathroom` branch adds a `_fix_wav_header()` that rewrites the RIFF/`data` chunk sizes — see `docs/branches/REPEATED_BATHROOM.md`.)

### `voice/narrate.py` — exit-interview script generation

Turns a persona's real action trace into a first-person exit-interview line. With an Anthropic key it asks Claude for 1–3 first-person sentences **grounded in the ordered step captions + outcome + failure_reason** in the persona's language; without a key it falls back to a deterministic template that still references the actual captions/outcome.

- `_OUTCOME_PHRASE` maps each outcome to a phrase (`SUCCESS`→"I finally got it done", `STEP_BUDGET`→"I ran out of patience clicking around", `TIME_BUDGET`→"I ran out of time", `STUCK`→"I got stuck and gave up", `ERROR`→"something broke…").
- `_captions(result)` — the grounding source: `step.action.caption or step.action.raw` per step, non-empty, in order.
- `template_exit_interview(result, persona)` — deterministic fallback grounded in the trace (`"First I tried to …, then …"` + outcome phrase + optional failure reason).
- `_build_prompt(result, persona)` — the Claude prompt: role + persona name/blurb + numbered steps + outcome + failure_reason, with strong anti-hallucination instructions ("Ground every claim in the steps above; do not invent UI you never touched"), answer in `persona.language`.
- `write_exit_interview(result, persona, anthropic_key=None)` — no key → template immediately; with key → lazy `AsyncAnthropic`, `model = env ANTHROPIC_MODEL or "claude-sonnet-5"`, `messages.create(max_tokens=200)`, return `text or template`; **any exception → template** ("never hard-fail the demo").

### `voice/voices.py` — voice assignment / cloning

`assign_voices(personas, client, clone_samples=None) -> {persona_id: voice_id}`. Reliability-first: (1) explicit `persona.voice_id` wins; (2) optionally clone a bespoke voice from a ~10 s sample (`client.voice_create(...)`, swallowed on error); (3) hand out **distinct preset voices** from the catalog (`client.voice_get(include_catalog=True)`, robust `_extract_voice_ids`), cycling with `presets[i % len(presets)]`. If the catalog can't be fetched, unresolved personas are left unassigned (engine then uses the TTS default). On `main` this is a separate pre-processing step not wired into the engine (the `repeated-bathroom` branch wires `SwarmManager._assign_voices` to call it per run).

---

## Cross-cutting notes

- **Failure isolation is a theme.** `write_exit_interview` (broad `except` → template) and `assign_voices` (swallowed errors) are built so the live demo never hard-fails; report/heatmap builders guard every division. Only `GradiumVoiceEngine` deliberately raises (no key), and only fail-fast before mutation.
- **`ERROR` semantics differ by module.** In `builder.py` errors are excluded from the completion denominator but still get a survival row; in `heatmap.py` only `SUCCESS` is filtered — an `ERROR` *with* `failure_coords` would contribute a heat point.
- **No WAV synthesis logic in-repo (on `main`).** Ghostpanel trusts Gradium's `output_format:"wav"`; writes `raw_data` verbatim.
