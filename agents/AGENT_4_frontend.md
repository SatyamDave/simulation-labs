# AGENT 4 — Frontend (the live grid of dying users)

**Branch:** `agent/web`   **You own:** `web/**` (the entire Vite project)
**Never edit:** anything outside `web/`.

You build the demo. **This is where 20% of the score (Demo) is won.** The money shot: a grid of
persona browser tiles running live, freezing **red** at the exact pixel each one fails, then a
report where a synthetic grandmother explains in voice why she gave up. Read `VISION.md` for tone
and `CLAUDE.md` for the event/report shapes. You can build and verify **entirely offline** against
`fixtures/events.jsonl` and `fixtures/run.json` before the backend exists.

## Stack

Vite + React + TypeScript. Charts: follow the **`dataviz` skill** (load it before writing chart
code) for the survival curve / heatmap palette + accessibility. Keep dependencies light; inline
styles or a tiny CSS file are fine. No backend calls hardcoded — read the API base from an env var
(`VITE_API_BASE`, default `http://localhost:8000`).

## Files to create (all under `web/`)

```
web/
  package.json  vite.config.ts  tsconfig.json  index.html
  src/
    main.tsx  App.tsx  styles.css
    types.ts            # TS mirror of the RunEvent + RunReport shapes (from CLAUDE.md/contracts)
    api.ts              # POST /runs, GET /runs/{id}/report, openRunSocket(runId)
    useRunStream.ts     # hook: connect WS, reduce RunEvent[] → live per-persona state
    components/
      LaunchForm.tsx     # URL + task + persona multiselect → "Unleash the swarm"
      PersonaGrid.tsx    # the live grid
      PersonaTile.tsx    # one persona: streamed thumbnail, caption, status ring, RED freeze on fail
      SurvivalCurve.tsx  # who survived how far (dataviz)
      Heatmap.tsx        # abandonment points overlaid on the target screenshot
      ReportView.tsx     # survival + heatmap + video players + exit-interview audio
      OfflineDemo.tsx    # replays fixtures/events.jsonl for a no-backend demo
  public/
    fixtures/            # COPY of run.json + events.jsonl at build time (or import from ../../fixtures)
```

> You need the shapes from `shared/ghostpanel_contracts/contracts.py` — read it for field names,
> but re-declare them in `types.ts` (don't import Python). Keep `types.ts` byte-faithful to the
> contract: `RunEvent` is a discriminated union on `event`
> (`run_started|persona_started|step|persona_finished|run_finished`).

## Tasks

### 1. `types.ts` + `api.ts` + `useRunStream.ts`
- Mirror `RunEvent` (all five variants) and `RunReport`/`PersonaResult`/`SurvivalPoint`/`HeatPoint`.
- `api.ts`: `startRun({target_url, task, persona_ids})`, `getReport(runId)`,
  `openRunSocket(runId): WebSocket` (to `${VITE_API_BASE.replace('http','ws')}/ws/runs/${runId}`).
- `useRunStream(runId)`: subscribe, reduce events into
  `Record<personaId, {status, lastCaption, lastThumb, step, failure?}>` + a global run status.

### 2. `PersonaTile.tsx` — the heart of the demo
- Shows the persona name + which channels are degraded (little badges: 👁️ blur, 🎨 CVD, ✋ tremor…).
- Displays the **latest streamed thumbnail** (`StepEvent.thumbnail_b64` is a data URI) as the tile
  background; overlay the current `caption` ("Clicking 'Explore plans'").
- A status ring: running (pulsing), success (green), abandoned (**red**).
- **On `persona_finished` with a non-success outcome:** freeze the tile, tint it red, draw a
  marker at `failure_coords`, and stamp the step/`failure_reason` ("gave up at step 4").

### 3. `PersonaGrid.tsx` + `App.tsx`
- Responsive grid (2–4 cols) of tiles; a live "N/─ survived" counter; overall progress.
- `App.tsx` routes: Launch → Live grid → Report. Include an **"Offline demo"** button that runs
  `OfflineDemo` (replays `fixtures/events.jsonl` on a timer) so the demo works with no backend.

### 4. `SurvivalCurve.tsx` + `Heatmap.tsx` + `ReportView.tsx`
- **SurvivalCurve:** per-persona steps-survived / completion (bar or step chart). Use the dataviz
  palette; label outcomes clearly (success vs step/time budget vs stuck).
- **Heatmap:** overlay `heatmap_points` (from `RunReport`) on a screenshot of the target; radial
  gradient blobs weighted by `weight`. (For offline dev, overlay on `fixtures/sample_screenshot.png`.)
- **ReportView:** completion rate headline, survival curve, heatmap, a `<video>` per persona
  (`PersonaResult.video_path` → `/artifacts/...`), and an `<audio>` for each exit-interview
  (`audio_path`) with the transcript shown beside it.

### 5. Polish for the stage
Dark theme, big type, motion when a persona dies. It should look alive and a little haunted
(it's *Ghost*panel). Keep the layout responsive so it projects well.

## Verification (must pass before merge)

```bash
cd web && npm install && npm run build      # must succeed
npm run dev                                  # then:
```
- **Offline:** the "Offline demo" replays `fixtures/events.jsonl` — tiles animate, one persona
  freezes red at `(300,145)`, `ReportView` renders `fixtures/run.json` (survival curve with 6
  personas, heatmap over the sample screenshot, the grandma transcript). All with **no backend**.
- **Live:** with Agent 3 running, `LaunchForm` → real run → grid animates from the live WS →
  report loads from `GET /runs/{id}/report`.
- No console errors; `npm run build` produces `web/dist`.

## Done when
`npm run build` is clean, the offline demo is a self-contained showpiece, the live path works
against the real API, and you touched only `web/`.
