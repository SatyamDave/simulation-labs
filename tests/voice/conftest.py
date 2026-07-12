"""Shared fixtures for voice tests, built from fixtures/run.json.

(Deliberately duplicated in tests/report/conftest.py: the ownership map has no
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
def grandma_result(fixture_report) -> PersonaResult:
    return next(r for r in fixture_report.results if r.persona_id == "grandma-72")


@pytest.fixture()
def power_user_result(fixture_report) -> PersonaResult:
    return next(r for r in fixture_report.results if r.persona_id == "power-user")


@pytest.fixture()
def grandma_persona() -> PersonaConfig:
    return PersonaConfig(
        id="grandma-72",
        name="Margaret, 72",
        blurb="Retired teacher; reads every word; trusts big blue buttons.",
    )
