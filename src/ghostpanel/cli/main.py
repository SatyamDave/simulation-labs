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
import sys
from pathlib import Path
from typing import Optional

from ghostpanel_contracts import RunReport

from . import config as cfgmod
from . import (
    ci_output,
    driver,
    exit_codes,
    preflight,
    regression,
    render,
    replay,
    safety,
)

# Minimal GitHub Actions workflow written by `sim init` (never clobbers an
# existing file). It runs the gate the same way the marketing promises: one
# workflow, `sim gate` fails the build when users start abandoning.
_WORKFLOW_YAML = """\
# .github/workflows/simulate.yml — Simulation Labs behavioral gate
# Fails the build when your users start abandoning. Add a model key as a repo
# secret: GEMINI_API_KEY (free tier works) or HAI_API_KEY — either is auto-detected.
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
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: |
          pip install "ghostpanel @ git+https://github.com/SatyamDave/simulation-labs@main"
          python -m playwright install --with-deps chromium
      - run: python -m ghostpanel.cli gate --config sim.yml --flow signup
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
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
    """Preflight-validate (personas, output dir, URL, reachability, SSRF, model
    key), warn if the run will be rate-limited, then drive the swarm. Raises
    preflight.PreflightError or safety.UnsafeURLError before any time is burned."""
    preflight.run_preflight(params)
    notice = preflight.rate_limit_notice(params)
    if notice and progress:
        print(notice)
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
        hint = preflight.classify_run_error(outcome.error)
        if hint:
            print(hint)
        return exit_codes.RUN_ERROR
    report = outcome.report
    assert report is not None
    _write_json(params.out_dir / "report.json", report)
    if preflight.usable_results(report) == 0:
        print(
            f"no usable results: all {len(report.results)} personas hit infra "
            f"errors before acting — nothing to report."
        )
        first = next(
            (r.failure_reason for r in report.results if r.failure_reason), None
        )
        if first:
            print(f"first error: {first}")
        print(f"raw report (for debugging): {params.out_dir / 'report.json'}")
        return exit_codes.NO_RESULTS
    render.print_summary(report)
    print(f"report: {params.out_dir / 'report.json'}")
    return exit_codes.OK


def _obtain_report(args: argparse.Namespace, params: Optional[_RunParams]):
    """Return (report, run_params_or_None, exit_code_or_None). When `--from` is
    given, load an existing RunReport instead of running the swarm."""
    if getattr(args, "from_", None):
        loaded = _load_report(args.from_)
        # Same guard as a live run: a report where every persona hit an infra
        # error can't yield a trustworthy verdict — don't gate/baseline on it.
        if preflight.usable_results(loaded) == 0:
            print(
                "no usable results in the loaded report: every persona hit an "
                "infra error — cannot produce a gate verdict or baseline."
            )
            return None, None, exit_codes.NO_RESULTS
        return loaded, None, None
    assert params is not None
    outcome = _run_swarm(params, progress=not args.quiet)
    if outcome.error:
        print(f"run error: {outcome.error}")
        hint = preflight.classify_run_error(outcome.error)
        if hint:
            print(hint)
        return None, params, exit_codes.RUN_ERROR
    _write_json(params.out_dir / "report.json", outcome.report)
    if preflight.usable_results(outcome.report) == 0:
        print(
            "no usable results: all personas hit infra errors — cannot produce a "
            "gate verdict or baseline. Fix the run error above and re-run."
        )
        return None, params, exit_codes.NO_RESULTS
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
        report,
        baseline,
        fail_under=fail_under,
        margin=args.margin,
        functional_persona_ids=_functional_probe_ids(report),
    )
    ci_output.write_ci_outputs(report, result, out_dir)

    render.print_summary(report)
    if result.verdict == regression.FUNCTIONAL_FAIL:
        label = "FUNCTIONAL FAIL"
    elif result.verdict == regression.BEHAVIORAL_REGRESSION:
        label = "BEHAVIORAL REGRESSION"
    else:
        label = "PASS"
    print(f"gate: {label} — {result.reason}")
    return exit_codes.OK if result.passed else exit_codes.GATE_FAILED


def _functional_probe_ids(report: RunReport) -> set[str]:
    """The undegraded (no-perturbation) personas that ran — the functional/E2E
    probes. Loads the roster and keeps those with no active perturbations whose
    id appears in the report's survival curve. Empty => functional dimension not
    assessed (e.g. a run with only degraded personas)."""
    from ghostpanel.engine.personas import load_personas

    ran = {p.persona_id for p in report.survival}
    try:
        roster = load_personas(None)
    except Exception:  # noqa: BLE001 — never let probe detection break the gate
        return set()
    return {
        p.id for p in roster
        if p.id in ran and not getattr(p, "active_perturbations", None)
    }


_NO_KEY_MSG = """\
No model API key found. `sim try` drives real browser agents, so it needs one.
Bring your own — any of these works and `sim` auto-detects it:

  # Google Gemini — free tier, no card. Recommended to start:
  export GEMINI_API_KEY=...     # get one at https://aistudio.google.com/apikey

  # or H Company Holo:
  export HAI_API_KEY=...        # https://hcompany.ai

Then just re-run:  sim try"""


def _resolve_try_backend() -> Optional[str]:
    """Return the model backend for `sim try`, offering an interactive key paste
    when none is configured and we're on a real terminal (P3). In a non-tty
    (CI/piped) we never prompt — we print the copy/paste guidance and give up, so
    `sim try` stays scriptable. Only `sim try` calls this; `sim gate` is untouched."""
    from ghostpanel.engine.models.registry import detected_key_backend

    backend = detected_key_backend()
    if backend is not None:
        return backend

    # No key. Only prompt on an interactive terminal — never in CI.
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(_NO_KEY_MSG)
        return None

    import getpass

    print("`sim try` drives real browser agents, so it needs a model API key.")
    print("Get a FREE Google Gemini key — no card, ~30 seconds:")
    print("  https://aistudio.google.com/apikey\n")
    try:
        pasted = getpass.getpass("Paste your Gemini API key (hidden), or Enter to cancel: ").strip()
    except (EOFError, KeyboardInterrupt):
        pasted = ""
    if not pasted:
        print("\nNo key entered.\n" + _NO_KEY_MSG)
        return None

    os.environ["GEMINI_API_KEY"] = pasted
    print("→ key accepted (this session only — add it to .env or export it to persist)\n")
    return detected_key_backend()


def _ensure_chromium() -> bool:
    """Make sure Playwright's Chromium is present, installing it if missing (P2).
    `sim try` only — `sim gate` assumes CI ran `playwright install`. Returns False
    (with a clear one-line fix) if the browser can't be made available."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            exe = p.chromium.executable_path
        if exe and os.path.exists(exe):
            return True
    except Exception:
        pass  # fall through to install

    print("→ Setting up the headless browser (Chromium, ~150MB, one time)…")
    import subprocess

    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"], check=True
        )
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  couldn't auto-install Chromium ({exc}). Run this once, then re-run:")
        print("    python -m playwright install chromium")
        return False


def _distinct_failure_reasons(report: RunReport) -> list[str]:
    """The distinct, non-empty per-persona failure reasons — the real 'why' behind
    an all-infra-error run (a bad key, a 429, a network drop), which the summary
    table alone doesn't show."""
    seen: list[str] = []
    for r in report.results:
        reason = (r.failure_reason or "").strip()
        if reason and reason not in seen:
            seen.append(reason)
    return seen


def _surface_run_error(error: str) -> None:
    """Print a run-level error as a clean, human headline. A broken target already
    carries a full human sentence (Orion's marker) — show it as-is; otherwise label
    it and add an actionable hint when we recognise the cause."""
    if error and "target returned HTTP" in error:
        print(f"\n✗ {error}")
        return
    print(f"\nrun error: {error}")
    hint = preflight.classify_run_error(error)
    if hint:
        print(hint)


def _cmd_try(args: argparse.Namespace) -> int:
    """Zero-config proof it works. With NO key, replay a real recorded run instantly
    (no browser, no network) — the honest zero-config first impression. With a key
    (or `--live`), run the swarm live against the bundled signup flow."""
    from types import SimpleNamespace

    from ghostpanel.cli import demo_flow
    from ghostpanel.engine.models.registry import detected_key_backend

    backend = detected_key_backend()

    # Keyless (or explicit --replay): show a genuine recorded run in seconds. This
    # is what makes "pip install && sim try" a real result with no key/config.
    if getattr(args, "replay", False) or (backend is None and not getattr(args, "live", False)):
        if replay.play(delay=0 if args.quiet else 0.32, quiet=args.quiet):
            return exit_codes.OK
        # Cassette missing (should not happen — it ships in-package): fall through
        # to the live path, which will prompt/guide for a key.

    # Live run — needs a model key. `--live` with no key prompts (tty) or guides.
    if backend is None:
        backend = _resolve_try_backend()
        if backend is None:
            return exit_codes.MISSING_KEY

    if not _ensure_chromium():
        return exit_codes.RUN_ERROR

    print("Simulation Labs — behavioral gate demo")
    print(f"→ backend: {backend} (auto-detected from your key)")
    print("→ serving a demo signup flow and sending a swarm of degraded users at it…\n")

    out_dir = Path(args.out or ".sim-try")
    with demo_flow.DemoServer() as srv:
        params = SimpleNamespace(
            persona_ids=demo_flow.DEMO_PERSONAS,
            out_dir=out_dir,
            url=srv.url,
            task=demo_flow.DEMO_TASK,
            fixture=False,
            allow_private=True,
            allowlist=["127.0.0.1", "localhost"],
            rpm=None,
        )
        preflight.run_preflight(params)  # validates key/personas/output; localhost allowed
        if backend == "holo":
            print("(Holo free tier is ~5 rpm, so a 5-agent run takes a few minutes — grab a coffee.)\n")
        on_event = render.make_progress_printer() if not args.quiet else None
        outcome = driver.run_flow(
            url=srv.url, task=demo_flow.DEMO_TASK, persona_ids=demo_flow.DEMO_PERSONAS,
            out_dir=out_dir, fixture=False, rpm=None, on_event=on_event,
        )

    if outcome.error:
        _surface_run_error(outcome.error)
        return exit_codes.RUN_ERROR

    _write_json(out_dir / "report.json", outcome.report)
    if preflight.usable_results(outcome.report) == 0:
        print("\n✗ No agent could act — this is an infrastructure problem, not your flow:")
        reasons = _distinct_failure_reasons(outcome.report)
        for reason in reasons:
            print(f"    • {reason}")
        hint = preflight.classify_run_error(reasons[0] if reasons else None)
        if hint:
            print(f"  {hint}")
        return exit_codes.NO_RESULTS

    print()
    render.print_summary(outcome.report)
    report_html = next(iter(out_dir.glob("*/report.html")), None)
    print("\n✓ it works. That was real browser agents attempting a real signup flow.")
    if report_html:
        print(f"  open the full report:  {report_html}")
    print("\nNow point it at YOUR flow:")
    print('  sim gate --url https://your-app.com/signup --task "create an account"')
    print("  # exit 1 blocks the merge when your users start abandoning. Wire it into CI: sim init")
    return exit_codes.OK


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
        epilog=(
            "Canonical invocation (always works, no install step):\n"
            "  python -m ghostpanel.cli run --url https://your-app/signup --task \"sign up\"\n"
            "The `sim` / `ghostpanel` console scripts do the same once installed via\n"
            "`pip install -e .` (or `python -m pip install -e .`). Offline test:\n"
            "  python -m ghostpanel.cli run --fixture fixtures/hostile_form.html --task \"sign up\""
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_try = sub.add_parser("try", help="zero-config demo: replay a real recorded run (no key), or run it live with your key")
    p_try.add_argument("--out", help="output directory (default: .sim-try)")
    p_try.add_argument("--quiet", action="store_true", help="suppress live per-step progress")
    p_try.add_argument("--live", action="store_true",
                       help="force a live run against the bundled demo (needs a model key)")
    p_try.add_argument("--replay", action="store_true",
                       help="force replay of the recorded run even if a key is set")

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
    "try": _cmd_try,
    "init": _cmd_init,
    "run": _cmd_run,
    "gate": _cmd_gate,
    "baseline": _cmd_baseline,
}


def _load_dotenv() -> None:
    """Load a .env from the cwd (or above) so `GEMINI_API_KEY=...` etc. in a .env
    file "just work" without the developer having to `export` them. Best-effort:
    never clobber a variable already set in the real environment."""
    try:
        from dotenv import find_dotenv, load_dotenv  # from python-dotenv (a dependency)
        # usecwd=True: look for .env from the working directory the developer runs
        # `sim` in (and up), not from the installed package location.
        path = find_dotenv(usecwd=True)
        if path:
            load_dotenv(path, override=False)
    except Exception:  # noqa: BLE001 — a missing .env or dotenv is not fatal
        pass


def main(argv: list[str] | None = None) -> int:
    """Parse argv and run a subcommand. Returns a process exit code."""
    _load_dotenv()
    parser = _build_parser()
    args = parser.parse_args(argv)   # argparse exits(2) on bad args == CONFIG_ERROR
    handler = _DISPATCH[args.command]
    try:
        return handler(args)
    except preflight.PreflightError as exc:
        # Already a one-line, human, actionable message with its own exit code.
        print(exc.message)
        return exc.code
    except safety.UnsafeURLError as exc:
        print(f"unsafe URL refused: {exc}")
        return exit_codes.UNSAFE_URL
    except (ValueError, FileNotFoundError) as exc:
        print(f"config error: {exc}")
        return exit_codes.CONFIG_ERROR
    except KeyboardInterrupt:
        # Ctrl-C mid-run: exit cleanly, never dump a traceback in front of a client.
        print("\ninterrupted — run cancelled.")
        return exit_codes.INTERRUPTED
    except Exception as exc:  # noqa: BLE001 — last line of defence: never show a raw trace
        if os.environ.get("SIM_DEBUG"):
            import traceback
            traceback.print_exc()
        print(f"\nunexpected error: {type(exc).__name__}: {exc}")
        print(
            "this is a bug in sim, not your setup. Re-run with SIM_DEBUG=1 for the full "
            "trace, or report it: https://github.com/SatyamDave/simulation-labs/issues"
        )
        return exit_codes.RUN_ERROR


if __name__ == "__main__":  # `python -m ghostpanel.cli.main` mirrors `sim`
    import sys

    sys.exit(main(sys.argv[1:]))
