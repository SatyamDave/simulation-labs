"""HTTP + WebSocket routes.

The router reads its collaborators (SwarmManager, RunRegistry, WebSocketHub)
off `request.app.state` / `websocket.app.state`, which create_app() populates.
Static mounts (/artifacts, web/dist) live in app.py because they are app-level.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class RunRequest(BaseModel):
    target_url: str
    task: str
    persona_ids: Optional[list[str]] = None


class RunCreated(BaseModel):
    run_id: str


@router.post("/runs", response_model=RunCreated)
async def create_run(body: RunRequest, request: Request) -> RunCreated:
    """Start a swarm run in the background; returns immediately with run_id."""
    run_id = await request.app.state.swarm.start_run(
        body.target_url, body.task, body.persona_ids
    )
    return RunCreated(run_id=run_id)


@router.get("/runs")
async def list_runs(request: Request) -> list[dict[str, Any]]:
    return request.app.state.registry.list()


@router.get("/runs/{run_id}/report")
async def get_report(run_id: str, request: Request) -> dict[str, Any]:
    record = request.app.state.registry.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"unknown run {run_id!r}")
    if record.report is None:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} has no report yet")
    return record.report.model_dump(mode="json")


@router.websocket("/ws/runs/{run_id}")
async def run_events(websocket: WebSocket, run_id: str) -> None:
    """Subscribe to a run's RunEvent stream: backlog replay, then live."""
    hub = websocket.app.state.hub
    await websocket.accept()
    await hub.subscribe(run_id, websocket)
    try:
        while True:  # we never expect client messages; this just detects disconnect
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(run_id, websocket)
