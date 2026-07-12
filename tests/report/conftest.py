"""Shared fixtures for report tests, built from fixtures/run.json.

(Deliberately duplicated in tests/voice/conftest.py: the ownership map has no
shared tests/ root file Agent 5 may create, and pytest conftests are per-tree.)
"""

import json
from pathlib import Path

import pytest

from ghostpanel_contracts import PersonaConfig, PersonaResult, RunReport

FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures"


@pytest.fixture()
def fixture_report() -> RunReport:
    data = json.loads((FIXTURES / "run.json").read_text())
    data.pop("_comment", None)
    return RunReport.model_validate(data)


@pytest.fixture()
def fixture_results(fixture_report) -> list[PersonaResult]:
    return fixture_report.results


@pytest.fixture()
def fixture_personas(fixture_report) -> list[PersonaConfig]:
    return [
        PersonaConfig(id=s.persona_id, name=s.persona_name)
        for s in fixture_report.survival
    ]
