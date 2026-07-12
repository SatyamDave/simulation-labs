"""HTTP + WebSocket routes for the orchestrator.

- ``POST /runs``            start a swarm run (returns ``{run_id}``)
- ``WS   /ws/runs/{id}``    replay buffered events, then stream live RunEvents
- ``GET  /runs/{id}/report`` the cached RunReport JSON
- ``POST /runs/{id}/ask``   live voice Q&A with one persona of a finished run
- ``POST /runs/{id}/ask-audio`` same Q&A, but the question arrives as WAV bytes
- ``GET  /runs``           list of runs (id, target, completion_rate, status)
- ``GET  /policy``         NemoClaw policy relay (local file or live NVIDIA docs)
- ``GET  /leaderboard``    the Ghostpanel Index — scores across past runs
- ``GET  /personas``       the full persona roster (launch-form source of truth)
- ``GET  /healthz``        liveness

Artifacts (``/artifacts``) and the built frontend (``/``) are mounted in
``app.create_app`` since they are ``StaticFiles`` app-level mounts, not routes.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import yaml
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ghostpanel.engine.personas import load_personas
from ghostpanel.runner.policy import RequestPolicy
from ghostpanel_contracts import PersonaConfig, PersonaOutcome, PersonaResult

from .runs import RunRecord, RunStatus

router = APIRouter()

# The real NemoClaw schema docs — GET /policy relays these; it NEVER fabricates.
_NEMOCLAW_DOCS_URL = "https://docs.nvidia.com/nemoclaw/latest/llms.txt"


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


# ---------------------------------------------------------------------------
# Live voice Q&A (Gradium sponsor stretch): ask a persona about its run.
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    persona_id: str = Field(..., description="Persona to interview, e.g. 'grandma-72'.")
    question: str = Field(..., description="The judge's question, free text.")


def _step_captions(result: PersonaResult) -> list[str]:
    """Ordered human captions of what the persona actually did.

    Inlined rather than reusing ``ghostpanel.voice.narrate._captions``: that
    symbol is private to the sibling-owned voice module (which only exposes
    exit-interview generation), so the server keeps its own 4-line copy.
    """
    caps: list[str] = []
    for step in result.steps:
        cap = (step.action.caption or step.action.raw or "").strip()
        if cap:
            caps.append(cap)
    return caps


def _grounded_answer(persona: PersonaConfig, result: PersonaResult) -> str:
    """First-person answer grounded ONLY in the recorded trace — the exit
    interview transcript, the step captions, and the recorded failure_reason.
    Deterministic (no LLM), so it can never invent UI the persona never touched."""
    parts: list[str] = []
    if result.transcript:
        parts.append(result.transcript.strip())
    captions = _step_captions(result)
    if captions:
        if len(captions) == 1:
            parts.append(f"Concretely, all I did was {captions[0].lower().rstrip('.')}.")
        else:
            trail = ", then ".join(c.lower().rstrip(".") for c in captions[:8])
            parts.append(f"Step by step, what I actually did was: {trail}.")
    if result.outcome == PersonaOutcome.SUCCESS:
        parts.append("I did manage to finish in the end.")
    elif result.failure_reason:
        parts.append(f"I stopped because {result.failure_reason.rstrip('.')}.")
    if not parts:
        parts.append(
            "Honestly, I never got anywhere on that page, so there is not much I can tell you."
        )
    return " ".join(parts)


def _lookup_ask_target(
    request: Request, run_id: str, persona_id: str
) -> tuple[PersonaConfig, PersonaResult]:
    """Shared /ask + /ask-audio resolution: 404 unknown run/persona, 409 while
    the run is still in flight; returns the persona config and its result."""
    record: Optional[RunRecord] = request.app.state.runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown run_id.")
    if record.status != RunStatus.FINISHED or record.report is None:
        raise HTTPException(
            status_code=409,
            detail=f"Run not finished yet (status={record.status.value}).",
        )
    result = next(
        (r for r in record.report.results if r.persona_id == persona_id), None
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown persona_id for this run.")
    persona = next((p for p in record.personas if p.id == persona_id), None)
    if persona is None:
        # Report present without configs (e.g. seeded in tests) — a minimal
        # stand-in is enough: only voice_id/name are consulted downstream.
        persona = PersonaConfig(id=persona_id, name=persona_id)
    return persona, result


def _make_voice_engine(request: Request, run_id: str):
    """Construct the run's voice engine, or None when no factory is configured
    (no GRADIUM_API_KEY). May raise — callers decide whether that's fatal."""
    swarm = request.app.state.swarm
    factory = getattr(swarm, "voice_engine_factory", None) if swarm else None
    if factory is None:
        return None
    return factory(Path(swarm.artifact_dir) / run_id)


async def _mutter_url(engine, run_id: str, text: str, voice_id: Optional[str]) -> Optional[str]:
    """Best-effort TTS of the answer; None (never an error) when voice fails."""
    if engine is None:
        return None
    try:
        wav_path = await engine.mutter(text, voice_id)
        return f"/artifacts/{run_id}/{Path(wav_path).name}"
    except Exception:  # noqa: BLE001 - voice is best-effort; text still answers
        return None


@router.post("/runs/{run_id}/ask")
async def ask_persona(run_id: str, req: AskRequest, request: Request) -> dict:
    """Answer a question AS one persona of a finished run, grounded in its real
    action trace, and voice it via Gradium when configured. Without a voice
    engine (no GRADIUM_API_KEY) the text still comes back with ``audio_url: null``
    so the demo can read it aloud itself."""
    persona, result = _lookup_ask_target(request, run_id, req.persona_id)
    text = _grounded_answer(persona, result)
    try:
        engine = _make_voice_engine(request, run_id)
    except Exception:  # noqa: BLE001 - engine construction is best-effort here
        engine = None
    audio_url = await _mutter_url(engine, run_id, text, persona.voice_id)
    return {"persona_id": req.persona_id, "text": text, "audio_url": audio_url}


_MAX_ASK_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB of WAV question is plenty


@router.post("/runs/{run_id}/ask-audio")
async def ask_persona_audio(run_id: str, persona_id: str, request: Request) -> dict:
    """Spoken variant of ``/ask``: the raw request body is the judge's question
    as WAV bytes (``Content-Type: audio/wav``), transcribed via the run's voice
    engine, then answered through the exact same grounded composition. Unlike
    ``/ask`` there is no text fallback — without a voice engine transcription
    is impossible, so this returns 503."""
    body = await request.body()
    if len(body) > _MAX_ASK_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio question too large (>{_MAX_ASK_AUDIO_BYTES} bytes).",
        )
    persona, result = _lookup_ask_target(request, run_id, persona_id)
    try:
        engine = _make_voice_engine(request, run_id)
    except Exception as exc:  # noqa: BLE001 - constructing the engine failed
        raise HTTPException(
            status_code=503, detail=f"Voice engine unavailable: {exc}"
        )
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Voice engine unavailable (GRADIUM_API_KEY not configured) — "
                "spoken questions cannot be transcribed. Use POST "
                f"/runs/{run_id}/ask with a text question instead."
            ),
        )
    try:
        question = await engine.transcribe(body)
    except Exception as exc:  # noqa: BLE001 - upstream STT failed
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}")

    text = _grounded_answer(persona, result)
    audio_url = await _mutter_url(engine, run_id, text, persona.voice_id)
    return {
        "persona_id": persona_id,
        "question": question,
        "text": text,
        "audio_url": audio_url,
    }


# ---------------------------------------------------------------------------
# NemoClaw policy relay (NVIDIA sponsor stretch).
# ---------------------------------------------------------------------------
@router.get("/policy")
async def get_policy(request: Request) -> dict:
    """Serve the NemoClaw policy actually in effect, never a fabricated one:
    a local YAML (``NEMOCLAW_POLICY_FILE`` env, else the settings-resolved
    preset — by default ``policies/ghostpanel-browse-only.yaml``), else the
    live schema docs from NVIDIA. 503 when neither source is retrievable.

    A loaded preset also gets a ``summary`` (name / allowed methods / hosts,
    via ``runner.policy.RequestPolicy``) and ``enforced`` says whether the
    swarm is running with the client-side mirror enforcement; ``gateway_url``
    / ``active`` keep reporting the real OpenShell routing."""
    settings = request.app.state.settings
    gateway_url = settings.nemoclaw_gateway_url.strip()
    swarm = request.app.state.swarm
    enforced = bool(swarm is not None and getattr(swarm, "request_policy", None))
    base = {"gateway_url": gateway_url, "active": bool(gateway_url), "enforced": enforced}

    policy_file = os.environ.get("NEMOCLAW_POLICY_FILE", "").strip()
    if not (policy_file and Path(policy_file).is_file()):
        settings_file = getattr(settings, "nemoclaw_policy_file", None)
        policy_file = (
            str(settings_file)
            if settings_file is not None and Path(settings_file).is_file()
            else ""
        )
    if policy_file:
        try:
            parsed = yaml.safe_load(Path(policy_file).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - bad YAML -> explicit 503, no guessing
            raise HTTPException(
                status_code=503,
                detail=f"NEMOCLAW_POLICY_FILE ({policy_file}) is not valid YAML: {exc}",
            )
        summary = None
        if isinstance(parsed, dict):
            mirror = RequestPolicy(parsed)
            if mirror.endpoints:  # only summarize real OpenShell presets
                summary = mirror.summary()
        return {**base, "source": "file", "policy": parsed, "summary": summary}

    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as http:
            resp = await http.get(_NEMOCLAW_DOCS_URL)
            resp.raise_for_status()
        return {**base, "source": "docs", "raw": resp.text}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=(
                "NemoClaw policy unavailable: no local NEMOCLAW_POLICY_FILE and the "
                f"live schema docs ({_NEMOCLAW_DOCS_URL}) could not be fetched "
                f"({type(exc).__name__}). Refusing to fabricate a policy."
            ),
        )


# ---------------------------------------------------------------------------
# The Ghostpanel Index — leaderboard across every scored run on disk.
# ---------------------------------------------------------------------------
_LEADERBOARD_CAP = 50


def _parse_generated_at(raw: object) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/leaderboard")
async def leaderboard(request: Request) -> list[dict]:
    """Newest-first scores from every ``<artifact_dir>/<run_id>/insights.json``.

    The ``meta`` / ``stats`` keys are written by the report module's insights
    (see ``ghostpanel.report.insights``); legacy insights files without them
    still list with nulls. Capped at the newest 50 entries."""
    artifact_dir = Path(request.app.state.settings.artifact_dir)
    rows: list[tuple[datetime, dict]] = []
    for path in artifact_dir.glob("*/insights.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a corrupt file never breaks the index
            continue
        if not isinstance(data, dict):
            continue
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
        run_stats = stats.get("run") if isinstance(stats.get("run"), dict) else {}
        agent = (
            data.get("agent_readiness")
            if isinstance(data.get("agent_readiness"), dict)
            else {}
        )

        # Persona count: meta.personas (report shape); legacy files -> null.
        personas = meta.get("personas")
        if not isinstance(personas, (int, float)):
            personas = None
        succeeded = run_stats.get("personas_succeeded")
        completion_rate = None
        if personas and isinstance(succeeded, (int, float)):
            completion_rate = succeeded / personas

        generated_at = meta.get("generated_at")
        sort_key = _parse_generated_at(generated_at) or datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        )
        rows.append(
            (
                sort_key,
                {
                    "run_id": meta.get("run_id") or path.parent.name,
                    "target_url": meta.get("target_url"),
                    "task": meta.get("task"),
                    "ghostpanel_score": data.get("ghostpanel_score"),
                    "agent_readiness_score": agent.get("score"),
                    "completion_rate": completion_rate,
                    "personas": personas,
                    "generated_at": generated_at if isinstance(generated_at, str) else None,
                },
            )
        )
    rows.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in rows[:_LEADERBOARD_CAP]]


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
