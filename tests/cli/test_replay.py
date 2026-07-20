"""Tests for the keyless `sim try` replay path (cli/replay.py + recorded_demo.py).

These lock the guarantees the launch relies on: the shipped cassette is a real,
parseable run; the replay renders it deterministically from stored data (no model,
no network); and the numbers a stranger sees match the embedded cassette exactly.
"""

from __future__ import annotations

import json

import pytest

from ghostpanel.cli import recorded_demo, replay
from ghostpanel_contracts import RunReport


def test_cassette_is_a_real_parseable_run() -> None:
    report = replay.load_cassette()
    assert isinstance(report, RunReport)
    assert report.survival, "cassette must carry a survival summary"
    # A real run of the bundled 5-persona demo.
    assert len(report.survival) == 5


def test_cassette_json_matches_embedded_report() -> None:
    """The parsed cassette must equal the raw embedded JSON — nothing is synthesized
    at load time; what ships is what plays."""
    raw = json.loads(recorded_demo.CASSETTE_JSON)
    report = replay.load_cassette()
    assert report.completion_rate == raw["completion_rate"]
    assert [s.persona_id for s in report.survival] == [s["persona_id"] for s in raw["survival"]]


def test_provenance_declares_backend() -> None:
    assert recorded_demo.PROVENANCE.get("backend"), "cassette must declare its backend for honest labeling"


def test_synth_events_cover_every_persona() -> None:
    report = replay.load_cassette()
    events = replay._synth_events(report)
    kinds = [e["event"] for e in events]
    assert kinds[0] == "run_started"
    assert kinds[-1] == "run_finished"
    started = {e["persona_id"] for e in events if e["event"] == "persona_started"}
    finished = {e["persona_id"] for e in events if e["event"] == "persona_finished"}
    ids = {s.persona_id for s in report.survival}
    assert started == ids
    assert finished == ids
    # Every finish carries the real outcome the report records.
    outcomes = {e["persona_id"]: e["outcome"] for e in events if e["event"] == "persona_finished"}
    for s in report.survival:
        assert outcomes[s.persona_id] == s.outcome.value


def test_play_is_deterministic_and_labels_recorded(capsys: pytest.CaptureFixture) -> None:
    assert replay.play(delay=0) is True
    first = capsys.readouterr().out
    assert replay.play(delay=0) is True
    second = capsys.readouterr().out
    assert first == second, "replay must be byte-for-byte deterministic"
    # The 'recorded run' label must be on the primary output (header), not hidden.
    assert "No key set" in first
    assert "recorded" in first.lower()
    # The completion rate shown must be the cassette's real number (working = PASS).
    report = replay.load_cassette()
    assert f"{report.completion_rate * 100:.0f}%" in first
    # When a broken cassette ships, the regression punchline must show the gate fails.
    if replay.load_broken_cassette() is not None:
        assert "gate FAIL" in first
        assert "gate PASS" in first


def test_play_calls_no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replay must never touch a model backend — it renders stored data only."""
    import ghostpanel.engine.models.registry as reg

    def _boom(*a, **k):  # pragma: no cover - fails the test if ever reached
        raise AssertionError("replay must not build/call a model backend")

    monkeypatch.setattr(reg, "build_model", _boom, raising=False)
    assert replay.play(delay=0) is True
