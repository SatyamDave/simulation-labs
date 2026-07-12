"""SurvivalReportBuilder — aggregate PersonaResults into a RunReport.

Implements the frozen `ReportBuilder` protocol. Survival math:

  * one SurvivalPoint per result (name looked up from the persona configs)
  * steps_survived = number of recorded steps (falls back to failure_step)
  * completion_rate = successes / non-ERROR personas — ERROR is an infra
    failure, not a human abandoning, so it is excluded from the denominator.
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

from ghostpanel.report.heatmap import build_heatmap


class SurvivalReportBuilder:
    """Concrete ReportBuilder (see CLAUDE.md class registry)."""

    def build(
        self,
        run_id: str,
        target_url: str,
        task: str,
        results: list[PersonaResult],
        personas: list[PersonaConfig],
    ) -> RunReport:
        name_by_id = {p.id: p.name for p in personas}

        survival = [
            SurvivalPoint(
                persona_id=r.persona_id,
                persona_name=name_by_id.get(r.persona_id, r.persona_id),
                outcome=r.outcome,
                steps_survived=len(r.steps) if r.steps else (r.failure_step or 0),
                completed=r.outcome == PersonaOutcome.SUCCESS,
            )
            for r in results
        ]

        # ERROR = infra crash, not a human giving up: exclude from the denominator.
        non_error = [r for r in results if r.outcome != PersonaOutcome.ERROR]
        successes = sum(1 for r in non_error if r.outcome == PersonaOutcome.SUCCESS)
        completion_rate = successes / len(non_error) if non_error else 0.0

        return RunReport(
            run_id=run_id,
            target_url=target_url,
            task=task,
            contract_version=CONTRACT_VERSION,
            results=results,
            survival=survival,
            heatmap_points=build_heatmap(results, personas),
            completion_rate=completion_rate,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
