# Web Frontend — `web/`

> **Owner:** Agent 4 (`agent/web`) · **Brand:** "simulation labs" · **Stack:** React 18 + Vite 6 + TypeScript 5 + Tailwind v4

A single-page React app that launches swarms of perceptually-degraded synthetic users against a target website and renders, in real time, a grid of them succeeding or abandoning — then a report showing completion rate, a survival breakdown, an abandonment heatmap, and per-persona video/voice exit interviews. Fully decoupled from the backend (REST + WebSocket, base URL injected at runtime) and ships a completely backend-free **offline demo** driven by committed fixtures.

---

## 1. Stack & tooling

- **React 18.3** (`createRoot` + `<StrictMode>`), **Vite 6** + `@vitejs/plugin-react`, **TypeScript 5.6** (strict, `noUnusedLocals`, `noFallthroughCasesInSwitch`).
- **Tailwind CSS v4** via `@tailwindcss/vite` — configured entirely in CSS (`@import "tailwindcss"`, `@theme`/`@theme inline`), **no `tailwind.config.js`**.
- **framer-motion** for entrance fades and pulsing status dots, wrapped in a global `<MotionConfig reducedMotion="user">`.
- Fonts: **Inter** + **IBM Plex Mono** (Google Fonts).

**Scripts:** `npm run dev` (Vite on :5173, `host: true`) · `npm run build` (`tsc --noEmit && vite build` → `dist/`) · `npm run preview`. Nothing about the backend is baked into the build — the API base is read at runtime.

**Entry:** `index.html` sets the title, an inline SVG favicon, and a critical **pre-paint theme script** that adds `.dark` to `<html>` before first paint from `localStorage.theme` (stored preference wins) falling back to `prefers-color-scheme`. Mounts at `#root` via `main.tsx`.

---

## 2. App structure ("routing")

No router. `App.tsx` is the whole shell; navigation is a single `Mode` variable:
```ts
type Mode = "launch" | "live" | "report" | "offline";
```
`App` state: `mode`, `runId`, `report`, `busy`, `error`, `loadingReport`, plus a local `useTheme()` (reads `.dark` from the DOM, `toggle()` flips the class + persists to `localStorage`).

Live stream is subscribed only while live: `const { state } = useRunStream(mode === "live" ? runId : null)`.

Transitions: `handleLaunch(v)` → `startRun` (POST `/runs`) → store `run_id` → `mode="live"` (on failure, a friendly error steering to the offline demo); `openLiveReport()` → `getReport` → `mode="report"`; `reset()` → back to launch (wired to the wordmark). Report view exists off the *live* path (`live` prop true); the offline demo renders its own `ReportView` internally.

---

## 3. Backend connection — `api.ts`

No URL is hardcoded. Base resolved once:
```ts
export const API_BASE =
  (import.meta.env.VITE_API_BASE)?.replace(/\/$/, "") ??
  (import.meta.env.DEV ? "http://localhost:8000" : "");   // "" = same-origin in prod
```

| Function | Endpoint | Notes |
|---|---|---|
| `startRun(payload)` | `POST /runs` | body `{target_url, task, persona_ids}` → `{run_id}` |
| `getReport(runId)` | `GET /runs/{id}/report` | throws on non-2xx |
| `openRunSocket(runId)` | `WS /ws/runs/{id}` | derives `ws(s)://` base; same-origin when `API_BASE=""` |
| `listPersonas()` | `GET /personas` | returns `null` (never throws) on failure → static catalog fallback |
| `artifactUrl(path?)` | — | resolves artifact paths against the backend host for `<video>`/`<audio>` |

---

## 4. `runReducer.ts` — the event-fold state machine

A **pure reducer** shared by both the live WS path and the offline replayer so they render identically. State = `LiveRunState` (`runId`, `targetUrl`, `task`, `status: idle|running|finished`, `order: string[]`, `personas: Record<id, PersonaLiveState>`, `completionRate`, `reportUrl`). Each `PersonaLiveState` = `{ persona, status: pending|running|success|abandoned, lastCaption, lastThumb, step, x?, y?, failure? }`.

`reduceEvent(prev, ev)` switches on `ev.event`:
- **`run_started`** — the only event that (re)creates the grid; seeds every persona `pending`.
- **`persona_started`** — flips to `running`, "Opening the page…".
- **`step`** — the workhorse: **refuses to resurrect a finished tile** (guards late/out-of-order frames); `x/y` and captions are **sticky** across frames (`?? cur.x`, `|| cur.lastCaption`) so partial frames don't blank the tile.
- **`persona_finished`** — `success` iff `outcome === "success"`, else `abandoned`; death `coords` falls back to the last streamed click.
- **`run_finished`** — `finished` + `completionRate` + `reportUrl` (shows the "View the report" button).

`tallies(state)` derives grid-header counts (`survived`/`dead`/`running`/`done`/`total`).

`useRunStream(runId)` opens the socket, folds each JSON frame via `reduceEvent`, tracks `wsStatus`, and tears down on unmount / `null`. Malformed frames are `console.warn`ed, not crashed. **No reconnect/backoff**; `wsStatus` is returned but `App` currently only uses `state`.

---

## 5. Components

- **`LaunchForm`** — landing/config. Fields: URL (default GitHub signup), task, and persona chips (all selected by default). On mount, `listPersonas()` opportunistically overrides the static `PERSONA_CATALOG`. Three quick-fill example chips (GitHub signup / Stripe register / bundled Hostile form). `canLaunch = url && task && selected.length && !busy`. Submits `{target_url, task, persona_ids}`.
- **`PersonaGrid`** — a quiet mono telemetry line (`tallies`) + a responsive grid of `PersonaTile`s in launch order; a "View the report" button when `reportReady`.
- **`PersonaTile`** — the live cell: header (name + perturbation tags), a 16/10 screenshot frame (`lastThumb` or a filtered fallback sample via `perceptionFilter`), a **death marker** (ring+dot placed by clamping `coords/space` to %, with a coord chip that flips left near the edge), a caption + mono outcome line, and a bottom `VitalLine`. `coordSpace` (default `1280×800`) is the pixel space of the coords.
- **`VitalLine` / `FlatlineGlyph`** — the one playful element: a 1px full-width sparkline per tile — a scrolling blip (running), a red line with a gap at the death point (abandoned), or a flat line (success/pending). `FlatlineGlyph` is the launch-page mark.
- **`SurvivalCurve`** — horizontal bars per persona (sorted by steps survived), colored by outcome via `theme.ts`.
- **`Heatmap`** — abandonment blobs. Two coord spaces hardcoded (`LIVE_SPACE 1280×800`, `SAMPLE_SPACE 640×480`); uses the live `target.png` backdrop when provided, else the bundled sample. Each point renders a soft radial blob (size scales with weight) + a precise ring marker.
- **`ReportView`** — the Notion-style report: big completion `%` (green >50 else red), "{survived} of {total} completed" (excludes `error`), an **agent-readiness verdict** (from the `ai-agent` persona), `SurvivalCurve`, `Heatmap`, and per-persona `ResultCard`s with `<video>`/`<audio>` receipts and the transcript. Media that 404s (no backend) degrades to a caption via `videoOk`/`audioOk`.
- **`OfflineDemo`** — zero-backend replay: loads fixtures, then a self-scheduling timer folds a synthetic timeline through `reduceEvent` (byte-identical to the live grid). Paces events (deaths land at 700 ms), then renders its own `ReportView` (omits `live` → bundled sample backdrop). `OFFLINE_SPACE = 640×480`.

---

## 6. The v3 "Quiet workspace (Notion × Ollama)" design system

Concept: a calm paper workspace, not an instrument panel; whitespace is the material; **exactly one playful touch** (the vital line). v3 removed the v2 instrument-panel language (bezel cards, scanlines, EKG traces, amber lamps, red borders, tinted washes, the bracketed `[simulation labs]` wordmark → plain lowercase mono).

Tokens live in `styles.css` (Tailwind v4 configured in CSS). Light-first `:root` + `.dark` custom properties: `--background`, `--surface`, `--card`, `--border` (hairline), `--foreground`, `--muted-foreground`, and **quiet functional hues** used only for dots/text/hairlines, never fills: `--live` (orange), `--ok` (green), `--fail` (red), `--idle` (gray) — lightened in dark mode for small-text AA contrast. Exposed to Tailwind utilities via `@theme inline` (`text-fail`, `bg-live`, etc.). Motion: the `vital-scroll` keyframe drifts the running trace left; a global `prefers-reduced-motion` kill-switch freezes animations legibly.

`theme.ts` bridges outcomes to tokens: `OUTCOME_COLOR` (CSS `var()` strings for charts), `OUTCOME_TEXT_CLASS` (Tailwind classes), literal hexes for the heatmap's alpha-composited gradients. `perturbationBadges(p)` produces the lowercase mono channel chips (prefers `active_perturbations`, else infers from numeric fields, else keyword-matches id/name/blurb). `perceptionFilter(p)` fakes the persona's degraded view on fixture thumbnails via a CSS `filter`.

---

## 7. Offline mode — `offline.ts` + fixtures

Reads two committed fixtures from `/public/fixtures`: `events.jsonl` (sparse: `run_started` with 6 personas, a few `step`s including grandma-72's load-bearing decoy click at `300,145`, `persona_finished`s, `run_finished` at `completion_rate 0.333`) and `run.json` (the full `RunReport` with `failure_coords`, transcripts, artifact paths). `loadOfflineDemo()` fetches both and calls `buildTimeline(runStarted, report)` which **enriches** the sparse events into a full parallel timeline (every tile animates), preserving the key beats verbatim (grandma freezes red at 300,145), then finishes in dramatic order (deaths first). `sample_screenshot.png` (640×480) is the tile/heatmap backdrop.

---

## 8. Types & gotchas

`types.ts` is a hand-maintained TypeScript mirror of `contracts.py` ("if these drift, contracts.py wins"). Key gotchas:
- **Only `success` counts as completion; `error` is infra and excluded** from survival stats.
- The `step` reducer **refuses to resurrect finished tiles** (out-of-order-frame safety).
- `x/y` and captions are **sticky** across frames.
- `GET /personas` is best-effort — the static `PERSONA_CATALOG` (ids must match backend `personas/*.json` slugs) is the guaranteed source.
- **Coordinate-space coupling:** live coords are `1280×800`, sample/offline `640×480`; every consumer must get the right `coordSpace` or death markers/heat blobs misplace.
- Media 404-degradation: receipts render as captions, not broken players, when the backend is absent.
- No router, no WS reconnect; `wsStatus` is unused by `App`.
