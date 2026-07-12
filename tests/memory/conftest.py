"""Shared fixtures for the memory tests: a hand-built RunReport + personas
covering success, abandonment, and error outcomes."""

from __future__ import annotations

import pytest
from ghostpanel_contracts import (
    PersonaConfig,
    PersonaOutcome,
    PersonaResult,
    PerturbationKind,
    RunReport,
    SurvivalPoint,
)


@pytest.fixture
def personas() -> list[PersonaConfig]:
    return [
        PersonaConfig(
            id="grandma-70",
            name="Margaret, 72",
            blur_sigma=3.0,
            active_perturbations=[PerturbationKind.BLUR, PerturbationKind.TREMOR],
        ),
        PersonaConfig(
            id="power-user",
            name="Alex",
            active_perturbations=[],  # baseline → impairment "none"
        ),
        PersonaConfig(
            id="impatient-mobile",
            name="Sam",
            active_perturbations=[PerturbationKind.IMPATIENCE],
        ),
        PersonaConfig(
            id="crashed-bot",
            name="Glitch",
            active_perturbations=[PerturbationKind.CVD],
        ),
    ]


@pytest.fixture
def report() -> RunReport:
    return RunReport(
        run_id="run-abc",
        target_url="https://www.Example.com/signup",
        task="sign up for an account",
        results=[
            # success
            PersonaResult(persona_id="power-user", outcome=PersonaOutcome.SUCCESS),
            # abandonment with coords + reason + transcript
            PersonaResult(
                persona_id="grandma-70",
                outcome=PersonaOutcome.STUCK,
                failure_coords=(412, 388),
                failure_step=7,
                failure_reason="couldn't find the submit button",
                transcript="I kept looking for a button but the text was too blurry to read.",
            ),
            # abandonment, no coords
            PersonaResult(
                persona_id="impatient-mobile",
                outcome=PersonaOutcome.TIME_BUDGET,
                failure_step=3,
                failure_reason="ran out of patience",
            ),
            # error — must be excluded everywhere
            PersonaResult(
                persona_id="crashed-bot",
                outcome=PersonaOutcome.ERROR,
                failure_reason="browser crashed",
            ),
        ],
        survival=[
            SurvivalPoint(
                persona_id="power-user",
                persona_name="Alex",
                outcome=PersonaOutcome.SUCCESS,
                steps_survived=12,
                completed=True,
            ),
            SurvivalPoint(
                persona_id="grandma-70",
                persona_name="Margaret, 72",
                outcome=PersonaOutcome.STUCK,
                steps_survived=7,
                completed=False,
            ),
            SurvivalPoint(
                persona_id="impatient-mobile",
                persona_name="Sam",
                outcome=PersonaOutcome.TIME_BUDGET,
                steps_survived=3,
                completed=False,
            ),
            SurvivalPoint(
                persona_id="crashed-bot",
                persona_name="Glitch",
                outcome=PersonaOutcome.ERROR,
                steps_survived=0,
                completed=False,
            ),
        ],
    )
