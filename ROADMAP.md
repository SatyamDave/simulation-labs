# Ghostpanel — 48-hour Roadmap

Five agents build in parallel on five branches against the **frozen contracts**. All can
start at T=0 because the contracts + skeleton are already committed. Order below is the
**integration/merge** sequence, not a "wait for each other" gate.

## Dependency / merge hierarchy

```
skeleton (DONE, on main: contracts + fixtures + docs)
    │
    ├── Agent 1  Engine          ── foundation (everyone depends on Action/PersonaAgent)
    │
    ├── Agent 2  Runner          ── depends on PersonaAgent contract (uses FakeHoloClient to test)
    ├── Agent 5  Voice + Report  ── depends on contracts only  ┐ fully parallel, contracts-only
    │                                                          ┘
    ├── Agent 3  Orchestrator    ── imports concrete classes from 1/2/5 (composition root)
    │
    └── Agent 4  Frontend        ── renders RunEvent/RunReport; dev against fixtures, then live
```

**Merge order:** `agent/engine` → `agent/runner` → `agent/voice-report` → `agent/server` →
`agent/web`. Each merges to `main` only when `pytest tests/test_contracts.py` + its own tests pass.

## Phase plan (target times; compress as needed)

### Phase 0 — Foundation (DONE, committed to `main`)
Frozen contracts, skeleton, fixtures (`hostile_form.html`, `sample_screenshot.png`, `run.json`,
`events.jsonl`), passing `tests/test_contracts.py`, docs, five work packages. Agents branch from here.

### Phase 1 — Vertical slice (first ~12h) — *"one persona dies on camera"*
Goal: a single persona runs end-to-end against `fixtures/hostile_form.html` and produces a video.
- **Agent 1:** `LiveHoloClient` (real Holo call returns coords) + `FakeHoloClient` + minimal
  `HoloPersonaAgent` (no perturbation yet) + `load_personas`.
- **Agent 2:** `PlaywrightSessionRunner` loop working with `FakeHoloClient`; video + step events.
- **Agent 3:** `POST /runs` runs **one** persona via the real wiring; WS emits events.
- **Agent 4:** live grid renders one tile from the WS stream (or `fixtures/events.jsonl` offline).
- **Agent 5:** `SurvivalReportBuilder.build` returns a valid `RunReport` from `fixtures/run.json`
  data; `GradiumVoiceEngine.exit_interview` produces one real `.wav`.
- **Milestone:** you can watch one persona click the decoy button and give up, on screen.

### Phase 2 — The swarm & the perturbations (next ~18h) — *"the grid of dying users"*
- **Agent 1:** all perturbations (blur, downscale-in-place, DaltonLens CVD, tremor jitter,
  literacy prompt-mod) + the 6–8 persona configs + the smart_resize coord handling.
- **Agent 2:** robustness — success/stuck/loop detection, budget enforcement, per-step thumbnails.
- **Agent 3:** true parallel swarm (`asyncio.gather`), shared Holo rate-limiter, report + voice
  triggered on completion, static serving of videos/audio/frontend.
- **Agent 4:** the money shot — N tiles live, freeze **red** with failing element + timestamp;
  survival curve + abandonment heatmap overlay + video players + exit-interview audio.
- **Agent 5:** exit-interview narration grounded in the action trace (Claude), distinct/cloned
  voice per persona, standalone HTML report; optional live "muttering."
- **Milestone:** point it at the hostile form (or a judge URL) and the whole grid runs + reports.

### Phase 3 — Sponsor polish & hardening (final ~12h)
- **NemoClaw (Agent 3, stretch):** route one persona's Holo inference through the OpenShell
  gateway; show the real (live-pulled) YAML policy blocking submit/egress.
- **Gradium (Agent 5):** semantic-VAD voice Q&A ("why did you quit?") for the demo.
- **All:** rehearse the 90-second demo against `hostile_form.html` as the guaranteed fallback;
  cache a second rehearsed target; tune persona count to the live Holo rate limit.

## Risk register (mitigations live in code)
- **Holo 10 RPM** → shared token-bucket in `LiveHoloClient` (`HAI_RPM`); run 4–6 personas if tight.
- **Live-demo faceplant** → `fixtures/hostile_form.html` is the always-works fallback target.
- **smart_resize coord drift** → keep image dims constant (see CLAUDE.md golden rule).
- **NemoClaw hardware** → hosted inference only; on-device Nemotron out of scope.

## Explicitly out of scope for the weekend
On-device Nemotron/local Holo weights (need a GPU); real account submission on third-party
sites; auth flows requiring 2FA; CI/CD.
