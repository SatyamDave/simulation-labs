"""Authed artifact proxy — closes the artifact IDOR (security-audit finding #2).

Artifacts (``report.html``, ``.webm`` videos, ``.wav`` audio, heatmap PNGs) are
tenant data. Instead of the old unauthenticated ``/artifacts`` static mount, they
are served here through a project-scoped route:

    GET /v2/runs/{run_id}/artifacts/{path:path}

Authorization is satisfied by **either**:
  * a caller (session cookie / bearer JWT / API key) who may access the run's
    project — reusing ``require_project_access`` (the same run-scoping pattern as
    ``routers/runs.py``); **or**
  * a valid short-lived ``?token=`` HMAC signature for this exact (run_id, path),
    so ``<img>``/``<video>``/``<a download>`` tags that cannot send an
    Authorization header can still load the artifact.

Neither ⇒ **404** (never 403) so we don't reveal that a run exists to a caller who
isn't entitled to it — matching the cross-tenant hiding used elsewhere.
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from ghostpanel.auth.artifact_tokens import sign_artifact, verify_artifact
from ghostpanel.auth.deps import require_project_access

router = APIRouter()


def _guess_media_type(rel_path: str) -> str:
    """Content-type from the file extension; octet-stream when unknown."""
    ctype, _ = mimetypes.guess_type(rel_path)
    return ctype or "application/octet-stream"


def signed_artifact_path(
    run_id: str, rel_path: str, secret: str, ttl_s: int = 3600
) -> str:
    """Build a self-authorizing artifact URL for the frontend / orchestrator.

    Returns ``/v2/runs/{run_id}/artifacts/{rel_path}?token=...`` where the token
    is an HMAC signature (via ``auth.artifact_tokens.sign_artifact``) that the
    route accepts in lieu of a session — for embedding in ``src``/``href``.
    """
    token = sign_artifact(run_id, rel_path, secret, ttl_s=ttl_s)
    return f"/v2/runs/{run_id}/artifacts/{rel_path}?token={token}"


@router.get("/v2/runs/{run_id}/artifacts/{path:path}")
async def get_artifact(run_id: str, path: str, request: Request) -> Response:
    store = request.app.state.store
    storage = request.app.state.storage
    settings = request.app.state.settings

    # Resolve the run first; unknown run → 404 (same as unauthorized, below).
    run = await store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Not found.")

    # (a) principal-based auth: session cookie / bearer JWT / API key scoped to
    #     the run's project. 401 (no creds) or 403 (wrong project) fall through
    #     to the signed-token path; any other HTTP error propagates.
    authorized = False
    try:
        await require_project_access(request, run.project_id)
        authorized = True
    except HTTPException as exc:
        if exc.status_code not in (401, 403):
            raise

    # (b) signed-URL auth: a valid, unexpired token for THIS run_id + path.
    if not authorized:
        token = request.query_params.get("token") or ""
        if token and verify_artifact(run_id, path, token, settings.session_secret):
            authorized = True

    if not authorized:
        # Hide existence from callers who aren't entitled to the run.
        raise HTTPException(status_code=404, detail="Not found.")

    # Prefer a backend presigned URL (S3) so the client fetches direct; local
    # storage returns None and we stream the (traversal-safe) bytes ourselves.
    url = storage.presigned_url(run_id, path)
    if url:
        return RedirectResponse(url)

    data = await storage.read(run_id, path)
    if data is None:
        raise HTTPException(status_code=404, detail="Not found.")
    return Response(content=data, media_type=_guess_media_type(path))


__all__ = ["router", "signed_artifact_path"]
