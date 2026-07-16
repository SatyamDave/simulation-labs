"""``/v2/projects`` — project CRUD + API-key management.

Owned by Agent P2-E. All project-scoped routes go through
``ghostpanel.auth.deps.require_project_access`` (session user OR API key that
belongs to the project); ``GET /`` and ``POST /`` use ``current_user``. Path
params are named ``project_id`` so ``require_project_access`` (whose signature is
``(request, project_id)``) resolves as a plain ``Depends`` with no shims.
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ghostpanel.auth.deps import current_user, require_project_access
from ghostpanel.store.models import ApiKey, Project, User

from .auth import ProjectOut

router = APIRouter(prefix="/v2/projects", tags=["projects"])


# --- response models --------------------------------------------------------
class ApiKeyOut(BaseModel):
    """An API-key row WITHOUT its hash (never leaked over the wire)."""

    id: str
    project_id: str
    name: str
    prefix: str
    created_at: Optional[_dt.datetime] = None
    last_used_at: Optional[_dt.datetime] = None
    revoked_at: Optional[_dt.datetime] = None

    @classmethod
    def from_row(cls, k: ApiKey) -> "ApiKeyOut":
        return cls(
            id=k.id,
            project_id=k.project_id,
            name=k.name,
            prefix=k.prefix,
            created_at=k.created_at,
            last_used_at=k.last_used_at,
            revoked_at=k.revoked_at,
        )


class ApiKeyCreatedOut(BaseModel):
    """Returned once at creation: the plaintext key plus the (hash-free) row."""

    key: str
    api_key: ApiKeyOut


# --- request models ---------------------------------------------------------
class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class CreateKeyRequest(BaseModel):
    name: str = Field("default", min_length=1, max_length=200)


# --- routes -----------------------------------------------------------------
@router.get("", response_model=list[ProjectOut])
async def list_projects(
    request: Request, user: User = Depends(current_user)
) -> list[ProjectOut]:
    store = request.app.state.store
    projects = await store.list_projects_for_user(user.id)
    return [ProjectOut.from_row(p) for p in projects]


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    body: CreateProjectRequest,
    request: Request,
    user: User = Depends(current_user),
) -> ProjectOut:
    store = request.app.state.store
    project = await store.create_project(owner=user, name=body.name.strip())
    return ProjectOut.from_row(project)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str, project: Project = Depends(require_project_access)
) -> ProjectOut:
    return ProjectOut.from_row(project)


# --- API keys ---------------------------------------------------------------
@router.post(
    "/{project_id}/keys", response_model=ApiKeyCreatedOut, status_code=201
)
async def create_key(
    project_id: str,
    body: CreateKeyRequest,
    request: Request,
    project: Project = Depends(require_project_access),
) -> ApiKeyCreatedOut:
    store = request.app.state.store
    row, plaintext = await store.create_api_key(project.id, body.name.strip())
    return ApiKeyCreatedOut(key=plaintext, api_key=ApiKeyOut.from_row(row))


@router.get("/{project_id}/keys", response_model=list[ApiKeyOut])
async def list_keys(
    project_id: str,
    request: Request,
    project: Project = Depends(require_project_access),
) -> list[ApiKeyOut]:
    store = request.app.state.store
    rows = await store.list_api_keys(project.id)
    return [ApiKeyOut.from_row(k) for k in rows]


@router.delete("/{project_id}/keys/{key_id}")
async def revoke_key(
    project_id: str,
    key_id: str,
    request: Request,
    project: Project = Depends(require_project_access),
) -> dict:
    store = request.app.state.store
    ok = await store.revoke_api_key(key_id, project.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown API key.")
    return {"ok": True, "id": key_id}
