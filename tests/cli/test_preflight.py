"""Tests for the founder-run preflight + in-run resilience (cli/preflight.py).

Every check must turn a failure into a one-line message + a *distinct* exit code,
never a traceback. These run fully offline: DNS and the SSRF guard are monkeypatched
where a live run would otherwise touch the network, and swarm runs go through a
patched `driver.run_flow` (no browser, no Holo).
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from ghostpanel_contracts import PersonaOutcome, PersonaResult, RunReport, SurvivalPoint

from ghostpanel.cli import exit_codes, preflight
from ghostpanel.cli.driver import RunOutcome
from ghostpanel.cli.main import main
from ghostpanel.server.config import get_settings

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "hostile_form.html"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _report(completion: float = 1.0, error_only: bool = False) -> RunReport:
    if error_only:
        return RunReport(
            run_id="r",
            target_url="file:///x",
            task="t",
            results=[
                PersonaResult(persona_id="fluent", outcome=PersonaOutcome.ERROR,
                              failure_reason="RuntimeError: browser exploded"),
                PersonaResult(persona_id="rushed", outcome=PersonaOutcome.ERROR,
                              failure_reason="RuntimeError: browser exploded"),
            ],
            completion_rate=0.0,
        )
    completed = completion >= 0.5
    return RunReport(
        run_id="r",
        target_url="file:///x",
        task="t",
        results=[PersonaResult(
            persona_id="fluent",
            outcome=PersonaOutcome.SUCCESS if completed else PersonaOutcome.STUCK,
        )],
        survival=[SurvivalPoint(
            persona_id="fluent", persona_name="Fluent",
            outcome=PersonaOutcome.SUCCESS if completed else PersonaOutcome.STUCK,
            steps_survived=8, completed=completed,
        )],
        completion_rate=completion,
    )


def _patch_run_flow(monkeypatch, outcome: RunOutcome):
    def _fake(*, url, task, persona_ids=None, out_dir, fixture=False,
              rpm=None, on_event=None):
        return RunOutcome(
            report=outcome.report, error=outcome.error,
            run_id="r", out_dir=Path(out_dir),
        )

    monkeypatch.setattr("ghostpanel.cli.main.driver.run_flow", _fake, raising=True)


# --------------------------------------------------------------------------- #
# unit: individual checks
# --------------------------------------------------------------------------- #
def test_check_personas_accepts_none_and_known():
    preflight.check_personas(None)              # full roster: no raise
    preflight.check_personas(["fluent", "rushed"])  # known ids: no raise


def test_check_personas_rejects_unknown_and_lists_valid():
    with pytest.raises(preflight.PreflightError) as ei:
        preflight.check_personas(["fluent", "grandma-72"])
    assert ei.value.code == exit_codes.UNKNOWN_PERSONA
    assert "grandma-72" in ei.value.message
    assert "fluent" in ei.value.message  # lists the valid ids


def test_check_output_dir_writable(tmp_path):
    preflight.check_output_dir(tmp_path / "sub" / "deep")  # no raise; created
    assert (tmp_path / "sub" / "deep").is_dir()


def test_check_output_dir_not_writable(tmp_path):
    afile = tmp_path / "afile"
    afile.write_text("x", encoding="utf-8")
    with pytest.raises(preflight.PreflightError) as ei:
        preflight.check_output_dir(afile / "cannot")  # parent is a file
    assert ei.value.code == exit_codes.OUTPUT_ERROR


@pytest.mark.parametrize("url", ["notaurl", "example.com/signup", "ftp://x/y"])
def test_check_url_wellformed_rejects_bad(url):
    with pytest.raises(preflight.PreflightError) as ei:
        preflight.check_url_wellformed(url)
    assert ei.value.code == exit_codes.CONFIG_ERROR


def test_check_url_wellformed_accepts_https():
    preflight.check_url_wellformed("https://app.example.com/signup")  # no raise


def test_check_reachable_dns_failure(monkeypatch):
    def _boom(*a, **k):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr("ghostpanel.cli.preflight.socket.getaddrinfo", _boom)
    with pytest.raises(preflight.PreflightError) as ei:
        preflight.check_reachable("https://nope.invalid/")
    assert ei.value.code == exit_codes.UNREACHABLE_URL


def test_check_model_key_missing(monkeypatch):
    monkeypatch.delenv("MODEL_BACKEND", raising=False)  # default -> holo
    monkeypatch.setenv("HAI_API_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(preflight.PreflightError) as ei:
            preflight.check_model_key()
        assert ei.value.code == exit_codes.MISSING_KEY
    finally:
        get_settings.cache_clear()


def test_check_model_key_skipped_for_echo_backend(monkeypatch):
    monkeypatch.setenv("MODEL_BACKEND", "echo")
    monkeypatch.setenv("HAI_API_KEY", "")
    get_settings.cache_clear()
    try:
        preflight.check_model_key()  # no raise: echo needs no vendor key
    finally:
        get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# unit: in-run resilience helpers
# --------------------------------------------------------------------------- #
def test_classify_run_error_rate_limit():
    hint = preflight.classify_run_error("openai.RateLimitError: 429 Too Many Requests")
    assert hint and "429" in hint


def test_classify_run_error_network():
    hint = preflight.classify_run_error("ConnectionError: connection timed out")
    assert hint and "network" in hint.lower()


def test_classify_run_error_unknown_is_none():
    assert preflight.classify_run_error("ValueError: something odd") is None
    assert preflight.classify_run_error(None) is None


def test_usable_results_excludes_errors():
    assert preflight.usable_results(_report(error_only=True)) == 0
    assert preflight.usable_results(_report(completion=1.0)) == 1


# --------------------------------------------------------------------------- #
# end-to-end through main(): each error path -> its exit code
# --------------------------------------------------------------------------- #
def test_run_unknown_persona_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["run", "--fixture", str(FIXTURE), "--task", "t",
               "--personas", "fluent,grandma-72", "--out", str(tmp_path / "o")])
    assert rc == exit_codes.UNKNOWN_PERSONA
    assert "grandma-72" in capsys.readouterr().out


def test_run_malformed_url_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["run", "--url", "notaurl", "--task", "t", "--out", str(tmp_path / "o")])
    assert rc == exit_codes.CONFIG_ERROR
    capsys.readouterr()


def test_run_unreachable_url_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    def _boom(*a, **k):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr("ghostpanel.cli.preflight.socket.getaddrinfo", _boom)
    rc = main(["run", "--url", "https://nope.invalid/", "--task", "t",
               "--out", str(tmp_path / "o")])
    assert rc == exit_codes.UNREACHABLE_URL
    capsys.readouterr()


def test_run_missing_key_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MODEL_BACKEND", raising=False)
    monkeypatch.setenv("HAI_API_KEY", "")
    get_settings.cache_clear()
    # skip the network-touching checks so we reach the key check deterministically
    monkeypatch.setattr("ghostpanel.cli.preflight.check_reachable", lambda url: None)
    monkeypatch.setattr("ghostpanel.cli.preflight.safety.assert_url_allowed",
                        lambda *a, **k: None)
    try:
        rc = main(["run", "--url", "https://app.example.com", "--task", "t",
                   "--out", str(tmp_path / "o")])
        assert rc == exit_codes.MISSING_KEY
    finally:
        get_settings.cache_clear()
    capsys.readouterr()


def test_run_unsafe_url_still_returns_unsafe_url(tmp_path, monkeypatch, capsys):
    """The SSRF refusal keeps its own distinct code even after preflight lands."""
    monkeypatch.chdir(tmp_path)
    rc = main(["run", "--url", "http://127.0.0.1/", "--task", "t",
               "--out", str(tmp_path / "o")])
    assert rc == exit_codes.UNSAFE_URL
    capsys.readouterr()


def test_run_zero_usable_results_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _patch_run_flow(monkeypatch, RunOutcome(report=_report(error_only=True),
                                            error=None, run_id="r",
                                            out_dir=tmp_path / "o"))
    rc = main(["run", "--fixture", str(FIXTURE), "--task", "t",
               "--out", str(tmp_path / "o")])
    assert rc == exit_codes.NO_RESULTS
    assert "no usable results" in capsys.readouterr().out


def test_run_error_prints_rate_limit_hint(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _patch_run_flow(monkeypatch, RunOutcome(
        report=None, error="RateLimitError: 429 Too Many Requests",
        run_id="r", out_dir=tmp_path / "o"))
    rc = main(["run", "--fixture", str(FIXTURE), "--task", "t",
               "--out", str(tmp_path / "o")])
    assert rc == exit_codes.RUN_ERROR
    assert "429" in capsys.readouterr().out
