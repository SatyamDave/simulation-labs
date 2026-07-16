"""``/v2/projects/{project_id}/members`` — seat / membership management.

Owned by Agent P4-B. Membership + seat side effects go through the frozen
``ghostpanel.billing.usage`` module (imported as a module so tests can
monkeypatch it); the seat quota is enforced with ``billing.entitlements``.

Auth:
  * list   — ``require_project_access`` (member of the project).
  * add    — the project **owner**; seat quota checked (``QuotaExceeded`` -> 402).
  * remove — the project **owner**; the owner's own seat can never be removed.
"""

from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ghostpanel.auth.deps import current_user, require_project_access
from ghostpanel.billing import usage
from ghostpanel.billing.entitlements import QuotaExceeded, check_can_add_seat
from ghostpanel.store.models import Project

router = APIRouter(prefix="/v2/projects", tags=["members"])


# --- models -----------------------------------------------------------------
class MemberOut(BaseModel):
    user_id: str
    email: str
    role: str


class AddMemberRequest(BaseModel):
    email: str = Field(..., min_length=1)
    role: str = "member"


# --- helpers ----------------------------------------------------------------
async def _require_owner(request: Request, project: Project) -> None:
    """Assert the calling session user owns ``project``; else 403."""
    user = await current_user(request)  # 401 if no session user
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="owner access required")


# --- routes -----------------------------------------------------------------
@router.get("/{project_id}/members", response_model=list[MemberOut])
async def list_members(
    project_id: str,
    project: Project = Depends(require_project_access),
) -> list[MemberOut]:
    members = await usage.list_members(project.id)
    return [MemberOut(user_id=m.user_id, email=m.email, role=m.role) for m in members]


@router.post("/{project_id}/members", response_model=MemberOut, status_code=201)
async def add_member(
    project_id: str,
    body: AddMemberRequest,
    request: Request,
    project: Project = Depends(require_project_access),
) -> MemberOut:
    await _require_owner(request, project)

    current_seats = await usage.member_count(project.id)
    try:
        check_can_add_seat(project.tier, current_seats)
    except QuotaExceeded as exc:
        raise HTTPException(status_code=402, detail=str(exc))

    try:
        member = await usage.add_member_by_email(
            project.id, body.email, body.role or "member"
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc) or "No such user.")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc) or "Already a member.")

    return MemberOut(user_id=member.user_id, email=member.email, role=member.role)


@router.delete("/{project_id}/members/{user_id}")
async def remove_member(
    project_id: str,
    user_id: str,
    request: Request,
    project: Project = Depends(require_project_access),
) -> dict:
    await _require_owner(request, project)
    ok = await usage.remove_member(project.id, user_id)
    if not ok:
        raise HTTPException(
            status_code=400, detail="Cannot remove this member (owner or not found)."
        )
    return {"ok": True, "user_id": user_id}
