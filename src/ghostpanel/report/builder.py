"""SurvivalReportBuilder — aggregate PersonaResults into a RunReport.

Implements the frozen `ReportBuilder` protocol. Turns a list of per-persona
action traces into a survival summary + abandonment heatmap. `ERROR` outcomes
are infra failures (not a real human "give up") and are excluded from the
completion-rate denominator.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ghostpanel_contracts import (
    CONTRACT_VERSION,
    PersonaConfig,
    PersonaOutcome,
    PersonaResult,
    RunReport,
    SurvivalPoint,
)

from .heatmap import build_heatmap


def _steps_survived(result: PersonaResult) -> int:
    """How far the persona got before dying: explicit failure step, else the
    number of steps recorded."""
    if result.failure_step is not None:
        return result.failure_step
    return len(result.steps)


class SurvivalReportBuilder:
    """Concrete `ReportBuilder`. Constructor takes no args (per the registry)."""

    def build(
        self,
        run_id: str,
        target_url: str,
        task: str,
        results: list[PersonaResult],
        personas: list[PersonaConfig],
    ) -> RunReport:
        name_by_id = {p.id: p.name for p in personas}

        survival: list[SurvivalPoint] = []
        for result in results:
            survival.append(
                SurvivalPoint(
                    persona_id=result.persona_id,
                    persona_name=name_by_id.get(result.persona_id, ""),
                    outcome=result.outcome,
                    steps_survived=_steps_survived(result),
                    completed=result.outcome == PersonaOutcome.SUCCESS,
                )
            )

        # completion_rate = successes / (personas that were NOT infra errors)
        non_error = [
            r for r in results if r.outcome != PersonaOutcome.ERROR
        ]
        successes = sum(
            1 for r in non_error if r.outcome == PersonaOutcome.SUCCESS
        )
        completion_rate = (successes / len(non_error)) if non_error else 0.0

        heatmap_points = build_heatmap(results)

        return RunReport(
            run_id=run_id,
            target_url=target_url,
            task=task,
            contract_version=CONTRACT_VERSION,
            results=results,
            survival=survival,
            heatmap_points=heatmap_points,
            completion_rate=completion_rate,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
