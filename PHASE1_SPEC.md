# Phase 1 spec — the `sim` CLI + `simulationlabs/gate` Action

> This is the frozen contract for Phase 1, built the same way the repo itself was:
> **parallel agents on disjoint paths, coding against locked interfaces.** Do not
> change a signature in this file without updating every owner. Do not edit files
> outside your ownership row.

## What we're shipping

The CI wedge the landing page sells: a developer adds one workflow file, and every
deploy runs the behavioral swarm against a real flow and **fails the build when users
start abandoning**. No backend — it runs on the customer's own `HAI_API_KEY`.

Public interface is fixed by the marketing on the landing page:
- Action: `simulationlabs/gate@v1`
- Inputs: `flow`, `icp`, `fail-under: last-passing` (regression vs. last-passing baseline)

## Ownership map (no path appears twice)

| Owner | Owns (create/edit ONLY these) | Reads (never edits) |
|-------|-------------------------------|---------------------|
| **Skeleton (orchestrator)** | `PHASE1_SPEC.md`, `cli/__init__.py`, `cli/exit_codes.py`, `cli/config.py`, `cli/__main__.py`, `pyproject.toml` | — |
| **Agent A — CLI core** | `cli/driver.py`, `cli/main.py`, `cli/render.py` | everything below (imports) |
| **Agent B — regression** | `cli/regression.py` | contracts, config |
| **Agent C — CI/safety** | `cli/ci_output.py`, `cli/safety.py` | contracts, config, regression |
| **Agent D — Action** | `action.yml`, `.github/workflows/simulate.yml` | — (calls the `sim` CLI by its flags) |
| **Agent E — docs** | `docs/ci.md`, `README.md`, `landing-page/index.html` | everything (reference only) |
| **Agent F — tests** | `tests/cli/**` | everything (imports + subprocess) |

`cli/*` means `src/ghostpanel/cli/*`. Never edit `shared/ghostpanel_contracts/**` or any
other agent's files. `pyproject.toml` and the foundation modules (`exit_codes`, `config`)
are written by the orchestrator and frozen — read them, don't edit them.

## The headless swarm driver (the linchpin — Agent A implements `driver.py`)

There is NO server in Phase 1. Drive the existing engine directly. Verified recipe:

```python
from playwright.async_api import async_playwright
from ghostpanel.server.swarm import SwarmManager
from ghostpanel.server.ws import WebSocketHub
from ghostpanel.server.runs import RunRegistry
from ghostpanel.engine.holo_client import LiveHoloClient, FakeHoloClient

async def _run(target_url, task, persona_ids, artifact_dir, holo, *, on_event=None):
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    hub = WebSocketHub(); registry = RunRegistry()
    swarm = SwarmManager(
        browser=browser, holo_client=holo, hub=hub, registry=registry,
        artifact_dir=artifact_dir,   # point at the output dir; _execute writes <id>/report.html here
        # voice OFF: pass no voice_engine_factory / voice_assigner, anthropic_key=None
    )
    run_id = await swarm.start_run(target_url, task, persona_ids)
    # live progress (optional): consume hub.subscribe(run_id) queue -> on_event(dict)
    await registry.get(run_id).task_handle      # blocks until the run is done
    await browser.close(); await pw.stop()
    rec = registry.get(run_id)
    return rec.report                            # RunReport | None (None => rec.error set)
```

Notes agents rely on:
- `SwarmManager.start_run(target_url, task, persona_ids) -> run_id`; `registry.get(run_id).task_handle`
  is an awaitable asyncio.Task. On success `rec.report` is a `RunReport`; on failure it is `None`
  and `rec.error` holds the message.
- `_execute` already writes `report.html` under `artifact_dir/<run_id>/`.
- Holo selection: `--fixture` / tests → `FakeHoloClient(scripted_actions=...)`; real runs →
  `LiveHoloClient(api_key, base_url, model, rpm)` from env (see `ghostpanel.server.config.get_settings`).
- `--fixture PATH` → `target_url = "file://" + abspath(PATH)`; the bundled `fixtures/hostile_form.html`
  declares success via `#ok`, so the swarm's success predicate already works against it.
- Persona ids: `None` → full roster; a list → those personas (`load_personas` handles unknowns).
- `HAI_RPM` (default 5) is the hard swarm cap — keep default swarms small (≤6 personas) and say so.

## Data shapes (from `ghostpanel_contracts` — do NOT redefine)

- `RunReport`: `run_id, target_url, task, results:[PersonaResult], survival:[SurvivalPoint],
  heatmap_points:[HeatPoint], completion_rate:float, generated_at:str`
- `SurvivalPoint`: `persona_id, persona_name, outcome:PersonaOutcome, steps_survived:int, completed:bool`
- `PersonaResult`: `persona_id, outcome, steps, failure_coords:(x,y)?, failure_step?, failure_reason,
  duration_s, video_path?, transcript, audio_path?`
- `PersonaOutcome`: `success | step_budget | time_budget | stuck | error`
  (only `success` counts as completion; `error` is infra failure — exclude from the survival denominator).
- `HeatPoint`: `x, y, weight, persona_id`

## Locked module interfaces

### `cli/exit_codes.py` (frozen — orchestrator)
`OK=0` (gate passed) · `GATE_FAILED=1` (regression / below threshold — the CI "block merge" signal) ·
`CONFIG_ERROR=2` · `RUN_ERROR=3` (swarm/infra crash) · `UNSAFE_URL=4`.

### `cli/config.py` (frozen — orchestrator)
`SimConfig`, `Flow`, `SwarmCfg`, `OutputCfg`, `SafetyCfg`, `IcpCfg` pydantic models;
`load_config(path: str|Path) -> SimConfig`; `DEFAULT_CONFIG_YAML: str`. `Flow.fail_under` is
`float | Literal["last-passing"]`. See the file for exact fields.

### `cli/safety.py` (Agent C)
```python
class UnsafeURLError(Exception): ...
def assert_url_allowed(url: str, *, allow_private: bool = False,
                       allowlist: list[str] | None = None) -> None:
    """Raise UnsafeURLError for non-http(s) schemes, loopback / private / link-local
    / reserved IPs (SSRF guard), or hosts not on a non-empty allowlist. file:// is allowed
    ONLY when allow_private=True (used by --fixture)."""
```

### `cli/regression.py` (Agent B)
```python
@dataclass
class PersonaDelta: persona_id: str; persona_name: str; was: bool; now: bool; steps_was: int; steps_now: int
@dataclass
class RegressionResult:
    passed: bool
    reason: str                      # human one-liner: why it passed/failed
    completion_now: float
    completion_baseline: float | None
    threshold: float                 # the effective numeric bar used
    fail_under: str                  # "last-passing" or the float as text (for display)
    regressed_personas: list[PersonaDelta]     # succeeded before, fail now
    new_dead_zones: list[tuple[int, int]]      # heat clusters absent from baseline
def compare(current: RunReport, baseline: RunReport | None, *,
            fail_under: float | str, margin: float = 0.0) -> RegressionResult:
    """fail_under is a float (0..1 absolute bar) OR "last-passing" (use baseline.completion_rate
    as the bar; margin tolerance). No baseline + "last-passing" => pass (first run seeds the baseline)."""
```

### `cli/ci_output.py` (Agent C)
```python
def summary_table(report: RunReport) -> str            # plain/ANSI console table, per-persona survival
def step_summary_md(report: RunReport, reg: RegressionResult) -> str   # $GITHUB_STEP_SUMMARY
def pr_comment_md(report: RunReport, reg: RegressionResult, *, report_url: str | None = None) -> str
def junit_xml(report: RunReport, reg: RegressionResult) -> str         # one <testcase> per flow/persona
def write_ci_outputs(report: RunReport, reg: RegressionResult, out_dir: Path) -> None
    # writes out_dir/{summary.md, pr-comment.md, junit.xml}; appends summary.md to
    # $GITHUB_STEP_SUMMARY when that env var is set. (summary_table lives here but is used by render.)
```
> `render.py` (Agent A) may import `summary_table` from here — that's the one cross-import allowed.

### `cli/driver.py` (Agent A)
```python
@dataclass
class RunOutcome: report: RunReport | None; error: str | None; run_id: str; out_dir: Path
def run_flow(*, url: str, task: str, persona_ids: list[str] | None, out_dir: Path,
             fixture: bool = False, rpm: int | None = None,
             on_event=None) -> RunOutcome            # sync wrapper (asyncio.run) around the recipe above
```

### `cli/main.py` (Agent A)
```python
def main(argv: list[str] | None = None) -> int       # argparse dispatch; returns an exit code
```
Subcommands (all return an exit code from `exit_codes`):
- `sim init` — write `sim.yml` + `.github/workflows/simulate.yml` if absent (never clobber).
- `sim run` — run a flow, write `<out>/report.json` + print `summary_table`. Flags:
  `--url --task --personas a,b,c --config sim.yml --out .sim --fixture PATH --rpm N`.
- `sim gate` — run (or `--from <report.json>`), `compare()` vs baseline/threshold, `write_ci_outputs`,
  print summary, **exit `GATE_FAILED` on failure**. Flags: `--fail-under last-passing|<float>`
  `--baseline .sim/baseline.json --margin 0.05` + all `run` flags.
- `sim baseline` — run (or `--from`), save the RunReport as `<out>/baseline.json`.

## Definition of done (per agent)
Your files implement the frozen signatures, `pytest tests/test_contracts.py` stays green,
and you touched only your ownership row. Do NOT run `git` (the orchestrator integrates + commits).
Agent A additionally verifies `python -m ghostpanel.cli run --fixture fixtures/hostile_form.html
--task "..." ` produces a report end-to-end (use a small persona set to respect the RPM cap).
