# Branch `repeated-bathroom` — the "god-tier round"

Everything below is present on `repeated-bathroom` (and `origin/repeated-bathroom`) but **not** on `main`. This branch diverged from the early trunk (`81f9ac8`, before the five-agent merge), so it lacks calico-leaf's integration and the sim-clock fix, but adds four major feature families in a single large commit (~+8,030 / −3,622 across 55 files, mostly under `web/`):

1. **NemoClaw / OpenShell network-policy enforcement** — a caged swarm that can browse but never submit/pay/exfiltrate.
2. **A run-insights / statistics engine** with a composite score, agent-readiness, and WCAG evidence.
3. **A multi-run Index (leaderboard) + Before/After Compare** experience.
4. **"Verified success"** + assorted sponsor stretch features.

---

## 1. NemoClaw / policy enforcement

A client-side **mirror** of NVIDIA's NemoClaw / OpenShell network-policy engine: only HTTP `GET` is allowed; every write verb (`POST/PUT/PATCH/DELETE`) is denied by default. Enforcement runs **inside the browser context** so it's verifiable in the demo even without the real OpenShell gateway.

- **Policy definition** — `policies/ghostpanel-browse-only.yaml`: an OpenShell preset (`enforcement: enforce`, allow-list `GET /**` on ports 80/443). The header documents the real gateway workflow it mirrors (`nemoclaw <sandbox> policy-add --from-file …`) and deliberately does **not** ship NemoClaw itself.
- **Engine** — `src/ghostpanel/runner/policy.py` (new): `RequestPolicy.allows(method, url)`. Semantics: within an `enforce` endpoint, `rules` are an allow-list (default-deny); `monitor` endpoints observe but never block; a host matched by **no** endpoint is **DENIED (fail-closed)**. Deliberately ignores port (browser dev/test traffic uses arbitrary localhost ports). `_path_glob_to_regex` (`**` crosses `/`, `*` within a segment); host globs via case-insensitive `fnmatch`. `from_file` **raises** on invalid YAML ("a misconfigured policy must fail loudly"). Exposes `summary()` for `GET /policy`.
- **Runner integration** — `PlaywrightSessionRunner.__init__(..., policy=None)`; when set, installs `context.route("**/*", _enforce)` that calls `policy.allows(...)` (**fails closed on exception**), `route.continue_()`/`route.abort("blockedbyclient")`, stamps `steps[-1].note = "policy_blocked"`, and emits a `StepEvent` captioned `🛡 Policy blocked <METHOD> <host>`. The runner tracks `state["current_step"]` to attribute a block to the right step.
- **Wiring** — `Settings.nemoclaw_policy_file` (env `NEMOCLAW_POLICY_FILE`, else the bundled preset); `app.py` parses it once (loud failure) and passes `request_policy=` into `SwarmManager`, which wraps the default runner factory so every runner gets the policy.
- **`GET /policy` relay** (`server/api.py`) — **never fabricates** a policy: serves the local YAML (`{source:"file", policy, summary}`), else the **live NVIDIA schema docs** fetched from `https://docs.nvidia.com/nemoclaw/latest/llms.txt` (`{source:"docs", raw}`), else `503`. Always carries `{gateway_url, active, enforced}`.
- **UI** — `PolicyPanel.tsx` (new): a compact sandbox strip in the live view; fetches `GET /policy` once and **renders nothing** when absent/503, so offline demos stay clean; shows `🛡 NemoClaw sandbox: <preset>` + method list + a `gateway active/inactive · enforced/advisory` pill. `PersonaTile` gains a `badge--shield` counter `🛡{blockedSteps}` (incremented in `runReducer` whenever a `StepEvent` caption starts with `🛡`).
- **Tests + fixtures** — `tests/runner/test_policy.py` (259 lines) incl. a real headless-Chromium integration test proving a form POST is aborted before reaching a localhost server while GETs flow. `fixtures/payment_form.html` (new) — a "QuantumLeap checkout" whose Pay button issues a **real** `fetch("/charge", {method:"POST"})`, aborted by the policy: the NVIDIA stage demo.

---

## 2. Stats / insights engine

`src/ghostpanel/report/insights.py` (new, 464 lines) — `build_insights(report, personas) -> dict` is a **pure** function whose returned dict **is the frozen wire format**. Keys: `ghostpanel_score`, `agent_readiness`, `wcag_findings`, `summary`, `meta`, `stats`, `survival_series`.

- **Composite score (`ghostpanel_score`, 0–100)** — equal weight per non-error persona. `SUCCESS = 1.0`; a non-success earns partial credit `min(0.5, 0.5 * steps_survived / max_steps)` ("dying at step 2 drags the score down more than dying at 25"). ERROR personas excluded; all-errored → 0.
- **Agent readiness** — from the `ai-agent` control: `100` if it completed unimpaired, partial + "this site is not agent-ready" otherwise, `None` if no ai-agent ran.
- **Run stats (`stats.run`)** — `total_steps`, `total_duration_s`, `avg_latency_ms`, `p95_latency_ms` (nearest-rank), `actions_by_type`, `blocked_actions` (steps with `note == "policy_blocked"`), success/abandon/error counts, `median_steps_to_abandon`, `fastest_success_steps`. Latency population = steps with a real (>0) Holo round-trip only — fed by the new `StepRecord.latency_ms` that `session.py` now measures around `agent.decide()`.
- **Per-persona stats** — includes `max_repeated_action`, the **rage-click metric** (longest run of consecutive identical captions).
- **WCAG evidence** — `_WCAG_BY_PERTURBATION` maps each degraded channel to WCAG 2.2 success criteria (BLUR/DOWNSCALE → 1.4.3/1.4.4; CVD → 1.4.1/1.4.3; TREMOR → 2.5.8/2.4.7; SMALL_VIEWPORT → 1.4.10; IMPATIENCE → 2.2.1/2.4.6; LOW_LITERACY → 3.1.5/2.4.6; non-`en` → 3.1.2). Each finding carries `standard_ref = "9." + criterion` (EN 301 549 clause) and a grounded `evidence` string (trace facts first, risk framing last, ending "…not an automated conformance verdict."). Deduped by criterion, **capped at 2 per persona**; only abandoning personas produce findings.

`tests/report/test_insights.py` (487 lines, 27 tests) pins all arithmetic. `SwarmManager._write_insights` persists `<run_id>/insights.json`. `write_html_report` gains `insights=`/`personas=` and renders new sections (score headline, agent-readiness card, WCAG risk table, stat tiles, inline-SVG survival curve, per-persona breakdown); `tests/report/test_html_report.py` (253 lines) covers it.

**Frontend** — `insights.ts` (new, 439 lines) mirrors the wire format plus a **client-side fallback** (`computeFallbackStats`/`computeFallbackInsights`) so the offline demo and older runs still render the panels; server-computed values win when present. `StatsPanel.tsx` (new, 535 lines) is the dashboard: a KPI stat-tile row (completion %, avg/p95 latency, steps, duration, `🛡 policy-blocked` when >0, median-steps-to-abandon, fastest success), a hand-rolled inline-SVG **step-after survival curve** (1 or 2 overlaid series, hover crosshair), an actions-by-type bar chart, and a per-persona table with **Rage clicks** and **🛡 Blocked** columns. `ReportView` renders an `InsightsPanel` (Simulation Score hero + agent-readiness + `WcagEvidence` table) followed by `<StatsPanel>`.

---

## 3. Multi-run Index and Compare

- **`GET /leaderboard`** — scans every `<run_id>/insights.json` (newest-first, capped at 50); each row: `run_id`, `target_url`, `task`, `ghostpanel_score`, `agent_readiness_score`, `completion_rate`, `personas`, `generated_at`. Corrupt/legacy files degrade gracefully. `api.ts.getLeaderboard()` falls back to `GET /runs` when `/leaderboard` is absent. **Note:** `main`'s `GET /personas` endpoint is *removed* on this branch (and `listPersonas` deleted from `api.ts`).
- **`IndexView.tsx`** (new) — the "hall of shame" leaderboard (`mode==="index"`), sorted **worst score first**. Tagline: *"Behavioral agent-readiness — measured, not declared."*
- **`CompareView.tsx`** (new, 359 lines) — Before/After (`mode==="compare"`). Pick a baseline run; renders two Simulation Score heroes with a delta arrow, delta stat tiles (completion Δ pp, accessibility findings Δ), **overlaid stepped survival curves** (before vs after), and per-persona outcome pairs highlighting personas the fix **saved** (green) or **regressed** (red). This is what `fixtures/hostile_form_fixed.html` (new) — the "REMEDIATED twin" of `hostile_form.html` with a remediation ledger mapping each fix to a WCAG criterion — exists for. The predicate factory matches the fixed variant via a `?as=hostile_form.html` suffix and also matches `payment_form.html`.

`tests/server/test_policy_index.py` (196 lines) covers `/policy` file-mode + `/leaderboard` new-vs-legacy, the 50-cap, and empty state.

---

## 4. "Verified success" + sponsor features

- **Verified success ("Receipts, not vibes")** — the key behavioral change in `session.py`. Previously an `ANSWER` action immediately set `SUCCESS`; now, when a success predicate exists, a claimed completion **must be verified by it** — otherwise the step is noted `answer_unverified`, and if the persona keeps claiming done it's marked `STUCK` ("claimed the task was done, but the success signal never appeared"). Rationale: *"An agent whose payment was policy-blocked will happily answer 'done' — that must not count as success."* This ties the policy cage to the scoring.
- **Per-persona Gradium voices** — `voice/voices.py` `assign_voices(...)` hands out distinct preset voices (or clones); `SwarmManager._assign_voices` calls it per run, never overriding an explicit `voice_id`.
- **Live persona Q&A — `POST /runs/{id}/ask`** — answers a judge's question **as** a persona of a finished run. `_grounded_answer` is **deterministic (no LLM)** — strings together the exit-interview transcript + actual captions + failure_reason ("can never invent UI the persona never touched"); synthesizes audio via `engine.mutter(text, voice_id)` when Gradium is configured. Needed a new `GradiumVoiceEngine.mutter()`. (Exercised by tests / curl; not wired into `api.ts`.)
- **Holo output hardening** — `engine/holo_client.py` replaces the ad-hoc salvage with a general `_repair_json()` that fixes Holo 3.1's key-dropped coordinate shapes before `json.loads`; a click fallback takes the **last** coordinate pair rather than center-clicking; actions parse an optional `label`/`element`/`target` into richer captions. `tests/engine/test_parse_repair.py` (9 tests).
- **Gradium WAV-header fix** — `voice/gradium_voice.py._fix_wav_header()` rewrites the RIFF/`data` chunk sizes from the real byte length (Gradium's streamed WAVs carry placeholder sizes that break `<audio>` scrubbing). `tests/voice/test_wav_header.py` (3 tests).
- **Exit-interview polish** — `narrate.py` compresses consecutive repeated captions ("clicking X again and again").

`tests/server/test_sponsor_features.py` (307 lines) is the hermetic harness for grounded `/ask` text + Gradium audio, insights.json emission, and the `/policy` relay.

---

## 5. Other differences from main

- **Frontend reskin / IA** — `App.tsx` heavily rewritten: the Tailwind-class layout is replaced by a `.app`/`.brandbar` "Simulation Labs" shell with two new modes (`index`, `compare`), a live WS status pill, and the mounted `PolicyPanel`. `web/DESIGN_SYSTEM.md` (1767 lines) and `web/src/components/VitalLine.tsx` (181 lines) are **deleted**; `styles.css` grows ~+1,970 lines.
- **API base simplification** — `api.ts` drops the same-origin/dev-detection logic; `API_BASE = VITE_API_BASE || "http://localhost:8000"`.
- **`DEMO_PLAYBOOK.md`** (+216 lines) adds staged sections: the Ghostpanel Index, Before/After, the report reveal, the NemoClaw caged-swarm pitch, and a Judge-Q&A cheat-sheet.
