"""`sim` CLI entrypoint + argparse dispatch — Agent A owns this file.

`main(argv)` parses args, dispatches to the init/run/gate/baseline subcommands,
and returns an exit code from `exit_codes`. The signature is FROZEN (the
pyproject console_script + __main__.py call it).

Exception -> exit-code map (see PHASE1_SPEC.md):
  safety.UnsafeURLError        -> UNSAFE_URL
  config/usage / ValueError    -> CONFIG_ERROR
  RunOutcome.error (swarm)     -> RUN_ERROR
  clean gate failure           -> GATE_FAILED
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional

from ghostpanel_contracts import RunReport

from . import config as cfgmod
from . import ci_output, driver, exit_codes, regression, render, safety

# Minimal GitHub Actions workflow written by `sim init` (never clobbers an
# existing file). It runs the gate the same way the marketing promises: one
# workflow, `sim gate` fails the build when users start abandoning.
_WORKFLOW_YAML = """\
# .github/workflows/simulate.yml — Simulation Labs behavioral gate
name: simulate
on:
  pull_request:
  push:
    branches: [main]

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: simulationlabs/gate@v1
        with:
          flow: signup
          icp: auto
          fail-under: last-passing
        env:
          HAI_API_KEY: ${{ secrets.HAI_API_KEY }}
"""


# ---------------------------------------------------------------------------
# Config / parameter resolution
# ---------------------------------------------------------------------------
def _load_cfg(args: argparse.Namespace) -> Optional[cfgmod.SimConfig]:
    """Load `sim.yml` from --config, else the default `sim.yml` in cwd if present."""
    explicit = getattr(args, "config", None)
    if explicit:
        return cfgmod.load_config(explicit)
    default = Path("sim.yml")
    if default.is_file():
        return cfgmod.load_config(default)
    return None


class _RunParams:
    """Resolved inputs for a swarm run (flags override sim.yml)."""

    def __init__(self, args: argparse.Namespace) -> None:
        cfg = _load_cfg(args)
        # --flow selects a named flow from sim.yml; None -> the first flow.
        flow = cfg.flow(getattr(args, "flow", None)) if cfg is not None else None
        self.cfg = cfg
        self.flow = flow

        # --- URL + fixture ---
        fixture_path = getattr(args, "fixture", None)
        if fixture_path:
            self.fixture = True
            self.url = "file://" + os.path.abspath(fixture_path)
        else:
            self.fixture = False
            self.url = args.url or (flow.url if flow else None)
            if not self.url:
                raise ValueError(
                    "no target URL: pass --url, --fixture PATH, or a sim.yml flow"
                )

        # --- task ---
        self.task = args.task or (flow.task if flow else None)
        if not self.task:
            raise ValueError("no task: pass --task or provide a sim.yml flow")

        # --- personas (flags > flow override > icp > full roster) ---
        if args.personas:
            self.persona_ids: Optional[list[str]] = [
                p.strip() for p in args.personas.split(",") if p.strip()
            ]
        elif flow is not None and flow.personas:
            self.persona_ids = list(flow.personas)
        elif cfg is not None:
            self.persona_ids = cfg.icp.persona_ids()
        else:
            self.persona_ids = None
        # Respect the swarm's RPM budget: cap an explicit list to max_personas.
        if cfg is not None and self.persona_ids:
            cap = cfg.swarm.max_personas
            if cap and len(self.persona_ids) > cap:
                self.persona_ids = self.persona_ids[:cap]

        # --- output dir ---
        self.out_dir = Path(
            args.out if args.out else (cfg.output.dir if cfg else ".sim")
        )

        # --- rpm ---
        self.rpm = args.rpm if args.rpm is not None else (cfg.swarm.rpm if cfg else None)

        # --- safety ---
        self.allow_private = self.fixture or (cfg.safety.allow_private if cfg else False)
        self.allowlist = list(cfg.safety.allowlist) if cfg else None

    def fail_under(self, override: Optional[str]) -> float | str:
        """The effective fail-under: CLI flag > flow config > 'last-passing'."""
        raw = override if override is not None else (
            self.flow.fail_under if self.flow is not None else "last-passing"
        )
        return _parse_fail_under(raw)


def _parse_fail_under(raw) -> float | str:
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if text == "last-passing":
        return "last-passing"
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(
            f'--fail-under must be a number 0..1 or "last-passing" (got {raw!r})'
        ) from exc


def _load_report(path: str | Path) -> RunReport:
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"report file not found: {p}")
    try:
        return RunReport.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surface as a config error
        raise ValueError(f"could not parse RunReport from {p}: {exc}") from exc


def _write_json(path: Path, report: RunReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8"
    )


def _run_swarm(params: _RunParams, *, progress: bool) -> driver.RunOutcome:
    """Safety-check the URL, then drive the swarm. Raises UnsafeURLError."""
    safety.assert_url_allowed(
        params.url, allow_private=params.allow_private, allowlist=params.allowlist
    )
    on_event = render.make_progress_printer() if progress else None
    return driver.run_flow(
        url=params.url,
        task=params.task,
        persona_ids=params.persona_ids,
        out_dir=params.out_dir,
        fixture=params.fixture,
        rpm=params.rpm,
        on_event=on_event,
    )


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------
def _cmd_init(args: argparse.Namespace) -> int:
    wrote: list[str] = []
    skipped: list[str] = []

    sim_yml = Path("sim.yml")
    if sim_yml.exists():
        skipped.append("sim.yml")
    else:
        sim_yml.write_text(cfgmod.DEFAULT_CONFIG_YAML, encoding="utf-8")
        wrote.append("sim.yml")

    workflow = Path(".github/workflows/simulate.yml")
    if workflow.exists():
        skipped.append(str(workflow))
    else:
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(_WORKFLOW_YAML, encoding="utf-8")
        wrote.append(str(workflow))

    for f in wrote:
        print(f"created {f}")
    for f in skipped:
        print(f"exists, left unchanged: {f}")
    if wrote:
        print("\nEdit sim.yml, then run `sim gate` locally or in CI.")
    return exit_codes.OK


def _cmd_run(args: argparse.Namespace) -> int:
    params = _RunParams(args)
    outcome = _run_swarm(params, progress=not args.quiet)
    if outcome.error:
        print(f"run error: {outcome.error}")
        return exit_codes.RUN_ERROR
    report = outcome.report
    assert report is not None
    _write_json(params.out_dir / "report.json", report)
    render.print_summary(report)
    print(f"report: {params.out_dir / 'report.json'}")
    return exit_codes.OK


def _obtain_report(args: argparse.Namespace, params: Optional[_RunParams]):
    """Return (report, run_params_or_None, exit_code_or_None). When `--from` is
    given, load an existing RunReport instead of running the swarm."""
    if getattr(args, "from_", None):
        return _load_report(args.from_), None, None
    assert params is not None
    outcome = _run_swarm(params, progress=not args.quiet)
    if outcome.error:
        print(f"run error: {outcome.error}")
        return None, params, exit_codes.RUN_ERROR
    _write_json(params.out_dir / "report.json", outcome.report)
    return outcome.report, params, None


def _cmd_gate(args: argparse.Namespace) -> int:
    params = None if getattr(args, "from_", None) else _RunParams(args)
    report, params, err = _obtain_report(args, params)
    if err is not None:
        return err

    out_dir = params.out_dir if params is not None else Path(args.out or ".sim")

    # Baseline: explicit --baseline, else <out>/baseline.json if present.
    baseline_path = Path(args.baseline) if args.baseline else out_dir / "baseline.json"
    baseline = _load_report(baseline_path) if baseline_path.is_file() else None

    fail_under = (
        params.fail_under(args.fail_under)
        if params is not None
        else _parse_fail_under(args.fail_under if args.fail_under is not None else "last-passing")
    )

    result = regression.compare(
        report, baseline, fail_under=fail_under, margin=args.margin
    )
    ci_output.write_ci_outputs(report, result, out_dir)

    render.print_summary(report)
    verdict = "PASS" if result.passed else "FAIL"
    print(f"gate: {verdict} — {result.reason}")
    return exit_codes.OK if result.passed else exit_codes.GATE_FAILED


def _cmd_baseline(args: argparse.Namespace) -> int:
    params = None if getattr(args, "from_", None) else _RunParams(args)
    report, params, err = _obtain_report(args, params)
    if err is not None:
        return err

    out_dir = params.out_dir if params is not None else Path(args.out or ".sim")
    baseline_path = out_dir / "baseline.json"
    _write_json(baseline_path, report)
    print(f"saved baseline: {baseline_path} (completion {report.completion_rate * 100:.0f}%)")
    return exit_codes.OK


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------
def _add_run_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--flow", help="named flow from sim.yml to run (default: the first flow)")
    p.add_argument("--url", help="target URL (overrides sim.yml flow)")
    p.add_argument("--task", help="the behavioral goal (overrides sim.yml flow)")
    p.add_argument("--personas", help="comma-separated persona ids (e.g. grandma-72,tremor)")
    p.add_argument("--config", help="path to sim.yml (default: ./sim.yml if present)")
    p.add_argument("--out", help="output directory (default: .sim or output.dir)")
    p.add_argument("--fixture", metavar="PATH", help="run against a local HTML file (file://, offline Fake Holo)")
    p.add_argument("--rpm", type=int, help="shared Holo requests-per-minute cap")
    p.add_argument("--quiet", action="store_true", help="suppress live per-step progress")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sim",
        description="Simulation Labs — behavioral swarm CI gate.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="scaffold sim.yml + .github/workflows/simulate.yml")

    p_run = sub.add_parser("run", help="run a flow and write a report")
    _add_run_flags(p_run)

    p_gate = sub.add_parser("gate", help="run/compare vs baseline; exit 1 on regression")
    _add_run_flags(p_gate)
    p_gate.add_argument("--fail-under", dest="fail_under",
                        help='"last-passing" or an absolute completion bar 0..1')
    p_gate.add_argument("--baseline", help="baseline report (default: <out>/baseline.json)")
    p_gate.add_argument("--margin", type=float, default=0.0,
                        help="tolerated drop below last-passing (default 0.0)")
    p_gate.add_argument("--from", dest="from_", metavar="REPORT",
                        help="score an existing report.json instead of running")

    p_base = sub.add_parser("baseline", help="run/load and save <out>/baseline.json")
    _add_run_flags(p_base)
    p_base.add_argument("--from", dest="from_", metavar="REPORT",
                        help="save an existing report.json as the baseline")

    return parser


_DISPATCH = {
    "init": _cmd_init,
    "run": _cmd_run,
    "gate": _cmd_gate,
    "baseline": _cmd_baseline,
}


def main(argv: list[str] | None = None) -> int:
    """Parse argv and run a subcommand. Returns a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)   # argparse exits(2) on bad args == CONFIG_ERROR
    handler = _DISPATCH[args.command]
    try:
        return handler(args)
    except safety.UnsafeURLError as exc:
        print(f"unsafe URL refused: {exc}")
        return exit_codes.UNSAFE_URL
    except (ValueError, FileNotFoundError) as exc:
        print(f"config error: {exc}")
        return exit_codes.CONFIG_ERROR
