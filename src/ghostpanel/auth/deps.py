"""FastAPI auth dependencies. STUB — Agent P2-C. Signatures FROZEN (routers import).

Two auth modes:
  * session JWT (cookie ``sl_session`` or ``Authorization: Bearer <jwt>``) → a User,
    for the dashboard.
  * project API key (``Authorization: Bearer sl_live_...`` or ``X-API-Key``) → a
    Project, for the CLI / CI.
The ``Store`` is read from ``request.app.state.store`` and the secret from
``request.app.state.settings`` (set by the composition root at integration).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request

from ghostpanel.auth.apikeys import KEY_PREFIX
from ghostpanel.auth.tokens import InvalidToken, decode_session_token
from ghostpanel.store.models import Project, User

SESSION_COOKIE = "sl_session"


@dataclass
class Principal:
    """Who is calling: a dashboard user, an API-key-scoped project, or both."""
    user: Optional[User]
    project: Optional[Project]


def _bearer(request: Request) -> str:
    """Return the raw ``Authorization: Bearer <token>`` value, or ''."""
    header = request.headers.get("authorization") or ""
    parts = header.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return ""


def _session_token(request: Request) -> str:
    """Extract a session JWT from the cookie or a (non-api-key) bearer token."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        return cookie
    bearer = _bearer(request)
    # A bearer starting with the api-key prefix is a project key, not a JWT.
    if bearer and not bearer.startswith(KEY_PREFIX):
        return bearer
    return ""


def _api_key(request: Request) -> str:
    """Extract a project API key from a bearer token or the X-API-Key header."""
    bearer = _bearer(request)
    if bearer.startswith(KEY_PREFIX):
        return bearer
    header = request.headers.get("x-api-key")
    if header and header.strip():
        return header.strip()
    return ""


async def optional_user(request: Request) -> Optional[User]:
    """Session user or None (never raises) — for endpoints that adapt to auth."""
    token = _session_token(request)
    if not token:
        return None
    settings = request.app.state.settings
    try:
        user_id = decode_session_token(token, settings.session_secret)
    except InvalidToken:
        return None
    store = request.app.state.store
    return await store.get_user(user_id)


async def current_user(request: Request) -> User:
    """Resolve the session user or raise HTTPException(401)."""
    user = await optional_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


async def current_project(request: Request) -> Project:
    """Resolve the project from an API key (CLI/CI) or raise HTTPException(401)."""
    key = _api_key(request)
    if not key:
        raise HTTPException(status_code=401, detail="API key required")
    store = request.app.state.store
    project = await store.project_for_api_key(key)
    if project is None:
        raise HTTPException(status_code=401, detail="invalid API key")
    return project


async def require_project_access(request: Request, project_id: str) -> Project:
    """Resolve the caller (user session OR api key) and assert they may access
    ``project_id``; raise HTTPException(403) otherwise. Returns the Project."""
    store = request.app.state.store

    # 1) Dashboard user: must be a member of the project.
    user = await optional_user(request)
    if user is not None:
        role = await store.member_role(user.id, project_id)
        if role is not None:
            project = await store.get_project(project_id)
            if project is not None:
                return project
        raise HTTPException(status_code=403, detail="not a member of this project")

    # 2) API-key caller: the key's project must be exactly project_id.
    key = _api_key(request)
    if key:
        project = await store.project_for_api_key(key)
        if project is not None and project.id == project_id:
            return project
        raise HTTPException(status_code=403, detail="API key not scoped to this project")

    raise HTTPException(status_code=401, detail="authentication required")


__all__ = ["Principal", "current_user", "optional_user", "current_project",
           "require_project_access"]
