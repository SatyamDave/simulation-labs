"""``/v2/auth`` — dashboard session auth (signup / login / logout / me).

Owned by Agent P2-E. Uses the frozen ``Store`` (``request.app.state.store``),
``Settings`` (``request.app.state.settings``), the password hashing in
``ghostpanel.auth.passwords``, the JWT helpers in ``ghostpanel.auth.tokens``, and
the ``current_user`` dependency in ``ghostpanel.auth.deps``. Never returns raw ORM
objects — every response is a pydantic model.
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ghostpanel.auth.deps import current_user
from ghostpanel.auth.passwords import hash_password, verify_password
from ghostpanel.auth.tokens import issue_session_token
from ghostpanel.store.models import Project, User

router = APIRouter(prefix="/v2/auth", tags=["auth"])

SESSION_COOKIE = "sl_session"


# --- response models --------------------------------------------------------
class UserOut(BaseModel):
    id: str
    email: str
    created_at: Optional[_dt.datetime] = None

    @classmethod
    def from_row(cls, u: User) -> "UserOut":
        return cls(id=u.id, email=u.email, created_at=u.created_at)


class ProjectOut(BaseModel):
    id: str
    name: str
    owner_id: str
    tier: str
    created_at: Optional[_dt.datetime] = None

    @classmethod
    def from_row(cls, p: Project) -> "ProjectOut":
        tier = p.tier.value if hasattr(p.tier, "value") else str(p.tier)
        return cls(
            id=p.id, name=p.name, owner_id=p.owner_id, tier=tier,
            created_at=p.created_at,
        )


# --- request models ---------------------------------------------------------
class Credentials(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=1024)


class SignupResponse(BaseModel):
    user: UserOut
    project: ProjectOut
    token: str


class LoginResponse(BaseModel):
    user: UserOut
    token: str


class MeResponse(BaseModel):
    user: UserOut
    projects: list[ProjectOut]


def _issue(request: Request, user_id: str) -> str:
    settings = request.app.state.settings
    return issue_session_token(
        user_id,
        settings.session_secret,
        ttl_hours=settings.session_ttl_hours,
    )


def _set_cookie(request: Request, response: Response, token: str) -> None:
    settings = request.app.state.settings
    max_age = int(settings.session_ttl_hours) * 3600
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(
    creds: Credentials, request: Request, response: Response
) -> SignupResponse:
    store = request.app.state.store
    email = creds.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email is required.")
    existing = await store.get_user_by_email(email)
    if existing is not None:
        raise HTTPException(status_code=400, detail="Email already registered.")

    user: User = await store.create_user(email, hash_password(creds.password))
    project: Project = await store.create_project(owner=user, name="Default")
    token = _issue(request, user.id)
    _set_cookie(request, response, token)
    return SignupResponse(
        user=UserOut.from_row(user),
        project=ProjectOut.from_row(project),
        token=token,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    creds: Credentials, request: Request, response: Response
) -> LoginResponse:
    store = request.app.state.store
    email = creds.email.strip().lower()
    user: Optional[User] = await store.get_user_by_email(email)
    if user is None or not verify_password(creds.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = _issue(request, user.id)
    _set_cookie(request, response, token)
    return LoginResponse(user=UserOut.from_row(user), token=token)


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(request: Request, user: User = Depends(current_user)) -> MeResponse:
    store = request.app.state.store
    projects = await store.list_projects_for_user(user.id)
    return MeResponse(
        user=UserOut.from_row(user),
        projects=[ProjectOut.from_row(p) for p in projects],
    )
