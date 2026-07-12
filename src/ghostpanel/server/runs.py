"""In-memory run registry: run status + cached RunReport + task handle.

A process-local store is enough for the demo — one server, runs live in memory.
The swarm writes reports here; the API reads them back for ``GET /runs`` and
``GET /runs/{id}/report``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from ghostpanel_contracts import RunReport


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


@dataclass
class RunRecord:
    run_id: str
    target_url: str
    task: str
    persona_ids: list[str] = field(default_factory=list)
    status: RunStatus = RunStatus.PENDING
    report: Optional[RunReport] = None
    error: str = ""
    memory_mode: str = "off"
    # asyncio.Task driving the swarm (so tests / shutdown can await it).
    task_handle: Optional["asyncio.Task"] = None

    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "target_url": self.target_url,
            "task": self.task,
            "status": self.status.value,
            "completion_rate": (
                self.report.completion_rate if self.report is not None else None
            ),
            "persona_count": (
                len(self.report.results)
                if self.report is not None
                else len(self.persona_ids)
            ),
            "memory_mode": self.memory_mode,
        }


class RunRegistry:
    """Thread-of-control-safe (single event loop) registry of runs."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}

    def create(
        self,
        run_id: str,
        target_url: str,
        task: str,
        persona_ids: list[str],
        memory_mode: str = "off",
    ) -> RunRecord:
        record = RunRecord(
            run_id=run_id,
            target_url=target_url,
            task=task,
            persona_ids=list(persona_ids),
            status=RunStatus.RUNNING,
            memory_mode=memory_mode,
        )
        self._runs[run_id] = record
        return record

    def get(self, run_id: str) -> Optional[RunRecord]:
        return self._runs.get(run_id)

    def set_report(self, run_id: str, report: RunReport) -> None:
        record = self._runs.get(run_id)
        if record is not None:
            record.report = report
            record.status = RunStatus.FINISHED

    def set_error(self, run_id: str, message: str) -> None:
        record = self._runs.get(run_id)
        if record is not None:
            record.status = RunStatus.ERROR
            record.error = message

    def list(self) -> list[dict]:
        return [r.summary() for r in self._runs.values()]

    def all_records(self) -> list[RunRecord]:
        return list(self._runs.values())
