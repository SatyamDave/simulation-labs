"""Tests for cli/main.py — argparse dispatch (Agent A).

main.py is a stub at time of writing, so the whole module is guarded with
xfail(strict=False) and flips to pass once Agent A lands. Runs are made
deterministic by monkeypatching `driver.run_flow` to return a canned RunOutcome
(no browser, no network); URL safety uses literal-IP / fixture paths so no DNS
is needed. capsys keeps command output off the test log.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostpanel_contracts import PersonaOutcome, RunReport, SurvivalPoint

from ghostpanel.cli import exit_codes
from ghostpanel.cli.driver import RunOutcome
from ghostpanel.cli.main import main

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "hostile_form.html"


def _report(completion: float) -> RunReport:
    completed = completion >= 0.5
    return RunReport(
        run_id="test-run",
        target_url="file:///x",
        task="t",
        survival=[
            SurvivalPoint(
                persona_id="power-user",
                persona_name="Alex",
                outcome=PersonaOutcome.SUCCESS if completed else PersonaOutcome.STUCK,
                steps_survived=8,
                completed=completed,
            ),
        ],
        completion_rate=completion,
    )


def _patch_run_flow(monkeypatch, report: RunReport):
    """Install a fake run_flow that ignores the world and returns `report`."""

    def _fake(*, url, task, persona_ids=None, out_dir, fixture=False,
              rpm=None, on_event=None):
        return RunOutcome(
            report=report, error=None, run_id="test-run", out_dir=Path(out_dir)
        )

    monkeypatch.setattr("ghostpanel.cli.driver.run_flow", _fake, raising=False)
    # main may import the symbol directly; patch there too if present.
    monkeypatch.setattr("ghostpanel.cli.main.run_flow", _fake, raising=False)


def _is_stub() -> bool:
    try:
        main(["__stubcheck__"])
    except NotImplementedError:
        return True
    except BaseException:
        return False
    return False


pytestmark = pytest.mark.xfail(
    _is_stub(), reason="pending Agent A main.py", strict=False
)


def test_init_writes_sim_yml_and_is_idempotent(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["init"])
    assert rc == exit_codes.OK
    sim_yml = tmp_path / "sim.yml"
    assert sim_yml.is_file()
    first = sim_yml.read_text(encoding="utf-8")

    # second call must not clobber an existing config
    rc2 = main(["init"])
    assert rc2 == exit_codes.OK
    assert sim_yml.read_text(encoding="utf-8") == first
    capsys.readouterr()


def test_run_writes_report_json_and_returns_ok(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / ".sim"
    _patch_run_flow(monkeypatch, _report(1.0))

    rc = main(
        ["run", "--fixture", str(FIXTURE), "--task", "sign up", "--out", str(out)]
    )
    assert rc == exit_codes.OK
    assert (out / "report.json").is_file()
    capsys.readouterr()


def test_gate_fails_below_absolute_threshold(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / ".sim"
    _patch_run_flow(monkeypatch, _report(0.0))  # 0% completion

    rc = main(
        [
            "gate", "--fixture", str(FIXTURE), "--task", "t",
            "--out", str(out), "--fail-under", "0.8",
        ]
    )
    assert rc == exit_codes.GATE_FAILED
    capsys.readouterr()


def test_gate_passes_above_absolute_threshold(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / ".sim"
    _patch_run_flow(monkeypatch, _report(1.0))  # 100% completion

    rc = main(
        [
            "gate", "--fixture", str(FIXTURE), "--task", "t",
            "--out", str(out), "--fail-under", "0.8",
        ]
    )
    assert rc == exit_codes.OK
    capsys.readouterr()


def test_unsafe_url_returns_unsafe_url_code(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / ".sim"
    _patch_run_flow(monkeypatch, _report(1.0))  # should never be reached

    rc = main(
        ["run", "--url", "http://127.0.0.1/", "--task", "t", "--out", str(out)]
    )
    assert rc == exit_codes.UNSAFE_URL
    capsys.readouterr()
