# Phase 3 spec — the customer dashboard

> Frozen contract for the hosted web dashboard. Parallel agents, disjoint paths.
> Everything new lives under `web/src/dashboard/`. Do NOT touch the existing demo
> (`web/src/App.tsx`, `web/src/components/*`, `web/src/api.ts`) except to READ/reuse.
> Do NOT edit `main.tsx`, `package.json`, `vite.config.ts`, or another agent's files.
> Do NOT run `git`. Work in `web/` (npm 11, node 26; react-router-dom@6, vitest@2,
> @testing-library/react installed).

## Goal
The hosted app a customer logs into: sign in, see run history, watch the
completion-trend-over-deploys line, drill into a stored run (grid/heatmap/report),
manage API keys, and author their `sim.yml`. The demo at `/` is untouched; the
dashboard mounts under `/app` (router added by the orchestrator).

## Frozen foundation (READ-ONLY — orchestrator owns)
- `web/src/dashboard/types2.ts` — User, Project, ApiKeyRow, CreatedApiKey,
  RunSummary2, EnqueuedRun, TrendPoint, Baseline, AuthResult, MeResult; re-exports RunReport.
- `web/src/dashboard/api2.ts` — the /v2 client: `signup/login/logout/me`,
  `listProjects/createProject/getProject`, `listKeys/createKey/revokeKey`,
  `listRuns/getRun/getRunReport/getRunTrend/getBaselines/setBaseline`,
  `artifactUrl`, `ApiError`. Token stored in localStorage; sent as Bearer.
- `web/src/dashboard/auth.tsx` — `AuthProvider` + `useAuth()` →
  `{ user, projects, activeProject, loading, login, signup, logout, setActiveProject, refreshProjects }`.

## Reuse (READ-ONLY) from the existing app
- `web/src/types.ts` — RunReport, PersonaResult, SurvivalPoint, HeatPoint, OUTCOME_LABELS.
- `web/src/components/SurvivalCurve.tsx`, `Heatmap.tsx`, `ReportView.tsx`, `PersonaGrid.tsx` —
  reuse in RunDetail if their props fit (import from `../../components/...`). If a prop shape
  doesn't fit a stored RunReport, render your own lightweight view rather than editing them.
- `web/src/personaCatalog.ts` — persona id/name/blurb catalog for the ICP picker.
- Match the existing Tailwind styling (tokens like `bg-hover`, `text-muted-foreground`,
  `text-foreground`, `border-border`) — read a couple of existing components first.

## Routing (orchestrator wires in main.tsx — agents just export components)
- `/login` → `pages/Login.tsx` default export
- `/signup` → `pages/Signup.tsx` default export
- `/app` → `DashboardLayout.tsx` default export (wrapped in `<RequireAuth>`), nested:
  - index → redirect to `runs`
  - `runs` → `pages/Runs.tsx` default export
  - `runs/:runId` → `pages/RunDetail.tsx` default export
  - `flows` → `pages/Flows.tsx` default export
  - `settings` → `pages/Settings.tsx` default export
Use `react-router-dom` v6 (`<Link>`, `useNavigate`, `useParams`, `<Outlet>`).

## Ownership map (no path appears twice; all under web/src/dashboard/)
| Owner | Owns |
|-------|------|
| **P3-B Auth pages** | `pages/Login.tsx`, `pages/Signup.tsx`, `components/RequireAuth.tsx` |
| **P3-C Shell + settings** | `DashboardLayout.tsx`, `components/ProjectSwitcher.tsx`, `pages/Settings.tsx` |
| **P3-D Runs + trend** | `pages/Runs.tsx`, `components/RunHistoryTable.tsx`, `components/TrendChart.tsx` |
| **P3-E Run detail** | `pages/RunDetail.tsx` |
| **P3-F Flows/ICP editor** | `pages/Flows.tsx`, `components/FlowEditor.tsx`, `components/IcpPicker.tsx` |
| **P3-G Tests** | `__tests__/**`, `test-setup.ts` |

## Behavior notes
- **RequireAuth**: while `useAuth().loading` show a spinner; if no `user`, `<Navigate to="/login">`; else `<Outlet/>`.
- **Login/Signup**: form (email/password), call `useAuth().login/signup`, on success `navigate("/app")`,
  on `ApiError` show the message. Link between the two. Password min 8 chars client-side.
- **DashboardLayout**: sidebar/nav (Runs, Flows, Settings) + a `ProjectSwitcher` (uses `projects`/
  `activeProject`/`setActiveProject`) + email + logout. `<Outlet/>` for the page. Dark/light aware.
- **Runs**: use `activeProject`; `listRuns(project.id, {flow, limit})`. Show `TrendChart` (from
  `getRunTrend` of the latest run, or per-flow) at top + `RunHistoryTable` (state, completion %,
  flow, when; row → `/app/runs/:id`). Empty state when no runs (explain: run `sim gate` in CI).
- **TrendChart**: small dependency-free SVG line of completion over time; mark regressions (a
  point below the previous) in the danger color. Accessible (title/desc).
- **RunDetail**: `getRun` + `getRunReport(runId)`; show completion, per-persona survival
  (reuse SurvivalCurve or a table), the abandonment heatmap (reuse Heatmap or render HeatPoints),
  links to the stored `report.html` / videos via `artifactUrl`, and a "set as baseline for <flow>"
  button (`setBaseline`). 425 (report not ready) → a "run still processing" state.
- **Settings**: project name + tier badge; API keys list (`listKeys`), create (`createKey` →
  show plaintext ONCE in a copy box with a "you won't see this again" warning), revoke.
- **Flows**: author a `sim.yml` — a `FlowEditor` (name/url/task/fail_under fields; multiple flows)
  + `IcpPicker` (multi-select personas from personaCatalog, or "auto") that renders live YAML to
  copy. This is a client-side config helper (no backend persistence endpoint exists yet — say so).

## Definition of done (per agent)
Components compile under `npx tsc --noEmit` with ZERO new errors, match the app's Tailwind
styling, handle loading/empty/error states, and are keyboard-accessible. You touched only your
row. No `git`. P3-G: add `test-setup.ts` + tests for api2 (mock fetch), auth context (login flow),
and at least one page render (RequireAuth redirect, Login submit) using @testing-library/react +
vitest jsdom; the orchestrator wires the `test` script + vitest config. Verify with
`npx tsc --noEmit` (report your files are clean).
