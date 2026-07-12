# Branch Topology & Lineage

All work landed on **2026-07-12**. Two authors: **SatyamDave** (scaffold + a first monolithic pass) and **Udaya Tejas** (the five-agent parallel build, integration, and all later reskins/fixes). Several AI-assisted commits are co-authored by `Claude Fable 5`.

There are **two live lineages** you care about:
- The **`main` / `debug` line** — the integrated five-agent system, UI reskins (v2 → v3), and the sim-clock patience fix. `origin/main` is the tip of this line.
- The **`repeated-bathroom` line** — a divergent "god-tier" sibling that forked *before* the five-agent merge and grew a different, larger feature set (NemoClaw policy cage, stats/WCAG insights, leaderboard, before/after compare). See `docs/branches/REPEATED_BATHROOM.md`.

---

## The scaffold (root)

`c7fe4f3` — **"Ghostpanel scaffold: frozen contracts + docs + 5-agent work packages"** (SatyamDave). The **root commit** (no parent). It committed `shared/ghostpanel_contracts/`, `pyproject.toml`, `CLAUDE.md`, `VISION.md`, fixtures, and empty `src/ghostpanel/**` package markers *before any agent started*, so five parallel branches never touch the same file. Parent of every agent branch and merge-base of essentially the whole tree.

---

## The five parallel agent branches (each forked off `c7fe4f3`)

All **local-only**, single-commit branches, each built strictly inside its owned path per the CLAUDE.md ownership map.

| Branch | Tip | Built |
|---|---|---|
| `agent/engine` | `f24684a` (+1,311) | `src/ghostpanel/engine/**` — `LiveHoloClient`/`FakeHoloClient`, `HoloPersonaAgent`, perturbations, prompts, the 8 personas + tests. |
| `agent/runner` | `480f540` (+838) | `src/ghostpanel/runner/**` — `PlaywrightSessionRunner`, execute, detect, thumbnail, testing + tests. |
| `agent/server` | `9766f30` (+1,293) | `src/ghostpanel/app.py` + `src/ghostpanel/server/**` — FastAPI, WS hub, swarm, config, `main`, `nemoclaw.md` + tests. |
| `agent/voice-report` | `f9e4ffb` (+1,063) | `src/ghostpanel/report/**` + `src/ghostpanel/voice/**` — `SurvivalReportBuilder`, `GradiumVoiceEngine`, narrate, voices + tests. |
| `agent/web` | `e2f5fd2` (+4,412) | the Vite/React `web/` app — grid, offline demo, report + fixtures. |

The five `worktree-agent-*` branches are ephemeral bookkeeping labels git created to host each agent's isolated worktree; they still resolve to the scaffold `c7fe4f3`. Safe to prune.

---

## `calico-leaf` — the integration merge (local-only)

Tip `c6a754c`. Forked from `c7fe4f3`, took `agent/runner` as its base, then merged the other four agents in sequence (`agent/engine` → `agent/voice-report` → `agent/server` → `agent/web`), plus integration fixes (artifact path nesting, artifact URLs in the report, HTML report + text-only exit interviews), the `GET /personas` roster endpoint, and the design-system restyle.

Its crown commit `c6a754c` — **"Fix Holo 3.1 live-API integration"** — records two things that live probing against `api.hcompany.ai` (`holo3-1-35b-a3b`) proved:
1. **It's a reasoning model** — `content` stays null until reasoning finishes, so small `max_tokens` yields `finish_reason=length` and an empty reply (token budgets raised, one length-retry, reasoning text used as last-resort answer).
2. **Coordinates are 0–1000 normalized, not pixels** — raw `(426,536)` vs ground-truth button centre `(547,430)` on a 1280×800 shot. This is the "verified live" coordinate fact enshrined in `CLAUDE.md`.

`calico-leaf` was then merged into the trunk at `a2e5b21`.

---

## The `main` line

Trunk lineage: `c7fe4f3 → b42a0b0` (SatyamDave's monolithic "implement all five modules") `→ efbb43d` (demo playbook) `→ 81f9ac8` (Rebrand to Simulation Labs) `→ ae75b72` (design-system spec) `→ a2e5b21` (**merge `calico-leaf`**) `→ 01cee21 → 3bb63c3 → d16789d → aab9845 → ddf784c` (port `/personas`, restyle, wire launch form, lint, salvage malformed Holo click JSON) `→ 8b1086e → 17eb398`.

| Branch | Tip | What it is |
|---|---|---|
| `memory-improvement` | `8b1086e` | **v2 instrument-panel UI.** Not divergent — an ancestor of `main`, one step before v3. |
| `design-system` | `17eb398` | **v3 quiet-workspace reskin** ("Notion × Ollama"), supersedes v2. On origin. |
| `main` (local) | `17eb398` | **Identical commit to `design-system` and `origin/design-system`.** One commit behind `origin/main`. |
| `debug` | `416e488` | **== `origin/main`.** Parent is `17eb398`; adds the sim-clock patience fix (below). |

**`debug` / `origin/main` — the sim-clock patience fix (`416e488`).** *The bug:* `deadline_s` was enforced as real wall-clock around the whole session, so the shared 5-RPM Holo limiter queue (~20–90 s/decision) consumed every persona's patience → ~90% of runs died `time_budget` regardless of the target page. *The fix (`runner/session.py`):* the runner charges a **simulated persona clock** — `_THINK_TIME_S = 4.0` s/step + *real page time*, **excluding `agent.decide()` wall time entirely**; `wait_for` is kept only as a `_WALL_CAP_S = 7200` s anti-hang guard mapped to `ERROR`, never `time_budget`; `duration_s` reports persona-experienced time. Plus post-action `_settle()`, a `frames_similar` no-change annotation, and stuck detection catching near-identical clicks within 14 px (which tremor jitter previously defeated). Verified live: power-user + tremor vs `hostile_form` finished in **54 simulated seconds** with **zero `time_budget` deaths** while individual Holo calls took up to 77 s wall-clock. (See `docs/modules/RUNNER.md §7`.)

---

## `repeated-bathroom` — the divergent "god-tier" line

Tip `ce82af5` — **"Ship the god-tier round: stats, WCAG evidence, NemoClaw enforcement, verified success."** On origin. **It diverged from the early trunk** (`ce82af5`'s parent is `81f9ac8`, "Rebrand to Simulation Labs"; `merge-base repeated-bathroom main = 81f9ac8`), so it never received calico-leaf's five-agent merge, the design-system reskins, or the sim-clock fix. Instead it is a single large commit that grew a different, larger feature set (~+8,030 / −3,622 across 55 files vs `main`). Full detail in `docs/branches/REPEATED_BATHROOM.md`.

---

## Which branches are on origin

- **On origin:** `origin/main` (= `debug` = `416e488`), `origin/design-system` (= local `main` = `design-system` = `17eb398`), `origin/repeated-bathroom` (= `ce82af5`). `origin/HEAD → origin/main`.
- **Local-only:** all five `agent/*`, all five `worktree-agent-*`, `calico-leaf`, `memory-improvement`.

---

## Commit graph

```
* 416e488  debug, origin/main, origin/HEAD  ── sim-clock patience fix
|
* 17eb398  main (local), design-system, origin/design-system  ── web v3 reskin
* 8b1086e  memory-improvement  ── web v2 instrument panel
* ddf784c  salvage malformed Holo click JSON
* aab9845  lint
* d16789d  wire launch form → GET /personas
* 3bb63c3  restyle web → Simulation Labs design system
* 01cee21  port GET /personas from calico-leaf
*   a2e5b21  Merge 'calico-leaf' into trunk
|\
| * c6a754c  calico-leaf  ── Holo 3.1 fix (reasoning model + 0–1000 coords)
| * 4536e68  restyle web → design system
| * fbf600a  GET /personas roster endpoint
| *   29dbdb3  Merge agent/web
| |\
| | * e2f5fd2  agent/web        (+4412) frontend: grid, offline demo, report
| * | 5103e79  lint
| * | 8fe18fb  integration: artifact paths, HTML report, text exit-interviews
| * |   d2b89cd  Merge agent/server
| |\ \
| | * | 9766f30  agent/server    (+1293) FastAPI, WS hub, swarm, composition root
| * |   3897a1b  Merge agent/voice-report
| |\ \
| | * | f9e4ffb  agent/voice-report (+1063) GradiumVoiceEngine, SurvivalReportBuilder
| * |   5789224  Merge agent/engine
| |\ \
| | * | f24684a  agent/engine    (+1311) Holo client, perturbations, 8 personas
| * / 480f540  agent/runner      (+838)  Playwright session runner  ← calico base
| |/
* | ae75b72  add design-system spec (from calico-leaf)
| |          * ce82af5  repeated-bathroom, origin/repeated-bathroom
| |         /            └─ "god-tier round": stats, WCAG, NemoClaw
* | 81f9ac8  Rebrand to Simulation Labs + real-website support   ← repeated-bathroom fork point
* | efbb43d  demo playbook + README
* | b42a0b0  implement all five modules (SatyamDave monolith)
|/
* c7fe4f3  worktree-agent-*(×5)  ── SCAFFOLD: frozen contracts + docs (ROOT)
```
