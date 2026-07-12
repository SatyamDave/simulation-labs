"""HTTP + WebSocket routes for the orchestrator.

- ``POST /runs``            start a swarm run (returns ``{run_id}``)
- ``WS   /ws/runs/{id}``    replay buffered events, then stream live RunEvents
- ``GET  /runs/{id}/report`` the cached RunReport JSON
- ``GET  /runs``           list of runs (id, target, completion_rate, status)
- ``GET  /personas``       the full persona roster (launch-form source of truth)
- ``GET  /healthz``        liveness

Artifacts (``/artifacts``) and the built frontend (``/``) are mounted in
``app.create_app`` since they are ``StaticFiles`` app-level mounts, not routes.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ghostpanel.engine.personas import load_personas

router = APIRouter()


class StartRunRequest(BaseModel):
    target_url: str = Field(..., description="URL the swarm should attempt.")
    task: str = Field(..., description="The goal, e.g. 'sign up for an account'.")
    persona_ids: Optional[list[str]] = Field(
        default=None,
        description="Subset of persona ids; omit/empty for the full roster.",
    )


class StartRunResponse(BaseModel):
    run_id: str


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/personas")
async def list_personas() -> list[dict]:
    """The full persona roster — the launch form's live source of truth."""
    return [p.model_dump(mode="json") for p in load_personas(None)]


@router.post("/runs", response_model=StartRunResponse)
async def start_run(req: StartRunRequest, request: Request) -> StartRunResponse:
    swarm = request.app.state.swarm
    if swarm is None:
        raise HTTPException(status_code=503, detail="Swarm not initialized.")
    run_id = await swarm.start_run(req.target_url, req.task, req.persona_ids)
    return StartRunResponse(run_id=run_id)


@router.get("/runs")
async def list_runs(request: Request) -> list[dict]:
    return request.app.state.runs.list()


@router.get("/runs/{run_id}/report")
async def get_report(run_id: str, request: Request) -> dict:
    record = request.app.state.runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown run_id.")
    if record.report is None:
        # Run is still in flight (or errored before producing a report).
        raise HTTPException(
            status_code=425,
            detail=f"Report not ready (status={record.status.value}).",
        )
    return record.report.model_dump(mode="json")


@router.websocket("/ws/runs/{run_id}")
async def ws_runs(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    hub = websocket.app.state.hub
    queue = hub.subscribe(run_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            if event.get("event") == "run_finished":
                # Terminal event delivered — close cleanly.
                break
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - client went away mid-send; nothing to do
        pass
    finally:
        hub.unsubscribe(run_id, queue)
