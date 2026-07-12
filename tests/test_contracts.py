"""Skeleton test: the frozen contracts import, round-trip, and the committed
fixtures validate against them. Every agent's CI-less local check starts green
here. Run:  pytest tests/test_contracts.py

This file is part of the skeleton (no single agent owns it); agents add their own
tests under tests/<module>/ and must not break these.
"""

import json
from pathlib import Path

import pydantic
import pytest

from ghostpanel_contracts import (
    CONTRACT_VERSION,
    Action,
    ActionType,
    PersonaConfig,
    PersonaFinished,
    PersonaOutcome,
    PersonaResult,
    RunReport,
    StepEvent,
    StepRecord,
)
from ghostpanel_contracts.contracts import RunEvent

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_contract_version():
    assert CONTRACT_VERSION == "1.0.0"


def test_action_roundtrip():
    a = Action(type=ActionType.CLICK, x=100, y=200, caption="Click Sign up", raw="Click(100, 200)")
    assert Action.model_validate(a.model_dump()) == a
    assert Action.model_validate_json(a.model_dump_json()).x == 100


def test_persona_config_defaults():
    p = PersonaConfig(id="grandma-72", name="Margaret, 72")
    assert p.viewport.width == 1280
    assert p.blur_sigma == 0.0
    # extra fields are forbidden — protects the contract from silent drift
    with pytest.raises(pydantic.ValidationError):
        PersonaConfig(id="x", name="y", not_a_field=1)


def test_persona_result_roundtrip():
    r = PersonaResult(
        persona_id="grandma-72",
        outcome=PersonaOutcome.STUCK,
        failure_coords=(300, 145),
        failure_step=4,
        steps=[
            StepRecord(
                persona_id="grandma-72",
                step=0,
                action=Action(type=ActionType.CLICK, x=1, y=2),
            )
        ],
    )
    assert PersonaResult.model_validate_json(r.model_dump_json()).failure_coords == (300, 145)


def test_run_event_discriminated_union():
    ta = pydantic.TypeAdapter(RunEvent)
    step = ta.validate_python(
        {"event": "step", "run_id": "r", "persona_id": "p", "step": 1, "caption": "x"}
    )
    assert isinstance(step, StepEvent)
    fin = ta.validate_python(
        {"event": "persona_finished", "run_id": "r", "persona_id": "p",
         "outcome": "success", "steps_survived": 3}
    )
    assert isinstance(fin, PersonaFinished)


def test_fixture_run_report_parses():
    data = json.loads((FIXTURES / "run.json").read_text())
    data.pop("_comment", None)
    report = RunReport.model_validate(data)
    assert report.run_id == "demo-run-0001"
    assert 0.0 <= report.completion_rate <= 1.0
    assert len(report.survival) == 6


def test_fixture_event_stream_parses():
    ta = pydantic.TypeAdapter(RunEvent)
    lines = (FIXTURES / "events.jsonl").read_text().strip().splitlines()
    events = [ta.validate_python(json.loads(ln)) for ln in lines]
    assert events[0].event.value == "run_started"
    assert events[-1].event.value == "run_finished"
