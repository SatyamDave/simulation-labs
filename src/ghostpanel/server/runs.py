"""In-memory run registry: run metadata + cached RunReport per run.

(The per-run *event* buffers live in ws.WebSocketHub, which replays them to
late WebSocket subscribers; this registry is the HTTP-facing state.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ghostpanel_contracts import RunReport

RUN_RUNNING = "running"
RUN_FINISHED = "finished"
RUN_FAILED = "failed"


@dataclass(slots=True)
class RunRecord:
    run_id: str
    target_url: str
    task: str
    status: str = RUN_RUNNING
    report: Optional[RunReport] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "target_url": self.target_url,
            "task": self.task,
            "status": self.status,
            "created_at": self.created_at,
            "completion_rate": self.report.completion_rate if self.report else None,
        }


class RunRegistry:
    """Process-local registry of runs. Single event loop → no locking needed."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}

    def create(self, run_id: str, target_url: str, task: str) -> RunRecord:
        record = RunRecord(run_id=run_id, target_url=target_url, task=task)
        self._runs[run_id] = record
        return record

    def get(self, run_id: str) -> Optional[RunRecord]:
        return self._runs.get(run_id)

    def set_report(self, run_id: str, report: RunReport) -> None:
        record = self._runs[run_id]
        record.report = report
        record.status = RUN_FINISHED

    def set_failed(self, run_id: str, reason: str = "") -> None:
        record = self._runs.get(run_id)
        if record is not None:
            record.status = RUN_FAILED

    def get_report(self, run_id: str) -> Optional[RunReport]:
        record = self._runs.get(run_id)
        return record.report if record else None

    def list(self) -> list[dict[str, Any]]:
        """Newest first — what GET /runs returns."""
        return [r.summary() for r in sorted(
            self._runs.values(), key=lambda r: r.created_at, reverse=True
        )]
