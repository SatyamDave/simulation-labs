"""``/v2`` — durable run submission, project-scoped history, and baselines.

Owned by Agent P2-E.

Auth model:
  * ``POST /v2/runs`` is CLI/CI: it authenticates via an **API key**
    (``current_project``) and enqueues a durable job — it creates no RunRow
    itself (the worker assigns ``run_id``).
  * The read endpoints are project-scoped. An API key pins the project directly;
    a dashboard **session user** must pass ``?project_id=`` for a project they are
    a member of (resolved through ``require_project_access``).
Every response is a pydantic model / plain JSON — never a raw ORM row.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ghostpanel.auth.deps import current_project, require_project_access
from ghostpanel.store.models import Project, RunRow, RunState

router = APIRouter(prefix="/v2", tags=["runs"])


# --- response models --------------------------------------------------------
class RunSummaryOut(BaseModel):
    id: str
    project_id: str
    state: str
    target_url: str
    task: str
    flow_name: str
    persona_ids: list[str] = Field(default_factory=list)
    completion_rate: Optional[float] = None
    error: str = ""
    created_at: Optional[_dt.datetime] = None
    finished_at: Optional[_dt.datetime] = None

    @classmethod
    def from_row(cls, r: RunRow) -> "RunSummaryOut":
        state = r.state.value if hasattr(r.state, "value") else str(r.state)
        return cls(
            id=r.id,
            project_id=r.project_id,
            state=state,
            target_url=r.target_url,
            task=r.task,
            flow_name=r.flow_name,
            persona_ids=list(r.persona_ids or []),
            completion_rate=r.completion_rate,
            error=r.error or "",
            created_at=r.created_at,
            finished_at=r.finished_at,
        )


class EnqueueResponse(BaseModel):
    job_id: str
    run_id: Optional[str] = None
    status: str = "queued"


class TrendPoint(BaseModel):
    t: _dt.datetime
    completion_rate: float


class BaselineOut(BaseModel):
    id: str
    project_id: str
    flow_name: str
    run_id: str
    completion_rate: float
    created_at: Optional[_dt.datetime] = None

    @classmethod
    def from_row(cls, b: Any) -> "BaselineOut":
        return cls(
            id=b.id,
            project_id=b.project_id,
            flow_name=b.flow_name,
            run_id=b.run_id,
            completion_rate=b.completion_rate,
            created_at=b.created_at,
        )


# --- request models ---------------------------------------------------------
class StartRunRequest(BaseModel):
    url: str = Field(..., min_length=1, description="Target URL the swarm attempts.")
    task: str = Field(..., min_length=1, description="The goal, e.g. 'sign up'.")
    persona_ids: Optional[list[str]] = None
    flow_name: str = ""


class SetBaselineRequest(BaseModel):
    flow_name: str = Field("", max_length=200)
    run_id: str = Field(..., min_length=1)


# --- helpers ----------------------------------------------------------------
async def _project_scope(request: Request, project_id: Optional[str]) -> Project:
    """API-key project when no ``project_id`` given; otherwise a project the
    session user (or API key) may access."""
    if project_id:
        return await require_project_access(request, project_id)
    return await current_project(request)


async def _run_in_scope(request: Request, run_id: str) -> tuple[Project, RunRow]:
    """Resolve a run the caller may see, or raise 404 (hiding existence of runs
    in other projects). Requires auth (401 propagates when the caller has none)."""
    store = request.app.state.store
    run = await store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown run.")
    try:
        project = await require_project_access(request, run.project_id)
    except HTTPException as exc:
        if exc.status_code == 403:
            raise HTTPException(status_code=404, detail="Unknown run.")
        raise
    return project, run


# --- run submission ---------------------------------------------------------
@router.post("/runs", response_model=EnqueueResponse, status_code=202)
async def start_run(
    body: StartRunRequest,
    request: Request,
    project: Project = Depends(current_project),
) -> EnqueueResponse:
    queue = request.app.state.queue
    spec: dict[str, Any] = {
        "url": body.url,
        "task": body.task,
        "persona_ids": list(body.persona_ids or []),
        "flow_name": body.flow_name or "",
    }
    job = await queue.enqueue(project.id, spec)
    return EnqueueResponse(
        job_id=job.id, run_id=job.run_id, status="queued"
    )


# --- run history ------------------------------------------------------------
@router.get("/runs", response_model=list[RunSummaryOut])
async def list_runs(
    request: Request,
    flow: Optional[str] = None,
    project_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[RunSummaryOut]:
    project = await _project_scope(request, project_id)
    store = request.app.state.store
    rows = await store.list_runs(
        project.id, flow_name=flow, limit=limit, offset=offset
    )
    return [RunSummaryOut.from_row(r) for r in rows]


@router.get("/runs/{run_id}", response_model=RunSummaryOut)
async def get_run(run_id: str, request: Request) -> RunSummaryOut:
    _project, run = await _run_in_scope(request, run_id)
    return RunSummaryOut.from_row(run)


@router.get("/runs/{run_id}/report")
async def get_run_report(run_id: str, request: Request) -> dict:
    _project, run = await _run_in_scope(request, run_id)
    finished = getattr(run.state, "value", run.state) == RunState.FINISHED.value
    if not finished or not run.report_json:
        state = getattr(run.state, "value", run.state)
        raise HTTPException(
            status_code=425, detail=f"Report not ready (state={state})."
        )
    return run.report_json


@router.get("/runs/{run_id}/trend", response_model=list[TrendPoint])
async def get_run_trend(
    run_id: str, request: Request, flow: Optional[str] = None
) -> list[TrendPoint]:
    project, run = await _run_in_scope(request, run_id)
    store = request.app.state.store
    flow_name = flow if flow is not None else run.flow_name
    series = await store.completion_trend(project.id, flow_name)
    return [TrendPoint(t=t, completion_rate=rate) for t, rate in series]


# --- baselines (project-scoped) ---------------------------------------------
@router.get("/projects/{project_id}/baselines")
async def get_baseline(
    project_id: str,
    request: Request,
    flow: str = "",
    project: Project = Depends(require_project_access),
) -> Optional[dict]:
    store = request.app.state.store
    row = await store.get_baseline(project.id, flow)
    return BaselineOut.from_row(row).model_dump(mode="json") if row else None


@router.post(
    "/projects/{project_id}/baselines", response_model=BaselineOut, status_code=201
)
async def set_baseline(
    project_id: str,
    body: SetBaselineRequest,
    request: Request,
    project: Project = Depends(require_project_access),
) -> BaselineOut:
    store = request.app.state.store
    run = await store.get_run(body.run_id)
    if run is None or run.project_id != project.id:
        raise HTTPException(status_code=404, detail="Unknown run for this project.")
    finished = getattr(run.state, "value", run.state) == RunState.FINISHED.value
    if not finished:
        raise HTTPException(
            status_code=425, detail="Run is not finished; cannot baseline it."
        )
    row = await store.set_baseline(project.id, body.flow_name, run)
    return BaselineOut.from_row(row)
