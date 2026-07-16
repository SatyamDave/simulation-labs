"""``/v2/auth`` account-recovery flows — password reset + email verification.

SEC-B (auth hardening). Both flows are **stateless**: the "link" a user gets is
a short-TTL HS256 JWT signed with ``settings.session_secret`` carrying a ``typ``
purpose claim (``"pwreset"`` / ``"verify"``) plus ``sub=user_id``. Nothing new is
persisted — validating the token is enough to authorize the action.

Design notes
------------
* **No user enumeration.** ``request-password-reset`` / ``request-verify`` always
  return 200 with an identical response shape whether or not the email exists. In
  dev (no mailer configured) the token is returned inline so the flow is testable;
  in prod it would be emailed instead. For unknown emails we still mint a token
  (bound to an opaque, non-existent subject) so the response is byte-for-shape
  identical — the token simply fails at redemption time.
* **Purpose-scoped tokens.** We validate ``typ`` on redemption, so a session JWT
  (no ``typ``) or a verify token can never be replayed as a password reset.
* The frozen ``User`` schema has no ``verified`` column, so ``verify-email`` is a
  stateless acknowledgement (validates the token + that the user still exists).
  ``Store`` exposes no password setter, so we update ``password_hash`` directly
  via ``db.session_scope`` here (permitted: this is our owned file).
"""

from __future__ import annotations

import datetime as _dt
import uuid

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ghostpanel.auth.passwords import hash_password
from ghostpanel.store import db
from ghostpanel.store.models import User

router = APIRouter(prefix="/v2/auth", tags=["auth"])

_ALGO = "HS256"
_TYP_PWRESET = "pwreset"
_TYP_VERIFY = "verify"
_RESET_TTL_MINUTES = 30
_VERIFY_TTL_MINUTES = 60 * 24  # 24h
_MIN_PASSWORD = 8

# Generic responses — kept identical for known/unknown emails (no enumeration).
_RESET_MESSAGE = "If that email is registered, a password-reset link has been sent."
_VERIFY_MESSAGE = "If that email is registered, a verification link has been sent."
_BAD_TOKEN = "This link is invalid or has expired. Please request a new one."


# --- token helpers (stateless; distinct short TTL + typ claim) --------------
def _issue_purpose_token(
    user_id: str, secret: str, typ: str, ttl_minutes: int
) -> str:
    """HS256 JWT with sub=user_id, a purpose ``typ`` claim, iat, and short exp."""
    if not secret:
        raise ValueError("secret must not be empty")
    now = _dt.datetime.now(_dt.timezone.utc)
    payload = {
        "sub": user_id,
        "typ": typ,
        "iat": now,
        "exp": now + _dt.timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, secret, algorithm=_ALGO)


def _decode_purpose_token(token: str, secret: str, expected_typ: str) -> str:
    """Verify signature/expiry AND that ``typ`` matches; return sub (user_id).

    Raises ``HTTPException(400)`` with a generic message on any failure so a
    caller cannot distinguish expired / tampered / wrong-purpose tokens.
    """
    if not secret:
        raise HTTPException(status_code=400, detail=_BAD_TOKEN)
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGO])
    except jwt.PyJWTError as exc:  # expired, bad signature, malformed
        raise HTTPException(status_code=400, detail=_BAD_TOKEN) from exc
    if payload.get("typ") != expected_typ:
        raise HTTPException(status_code=400, detail=_BAD_TOKEN)
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(status_code=400, detail=_BAD_TOKEN)
    return sub


async def _set_password_hash(user_id: str, new_hash: str) -> bool:
    """Update the user's ``password_hash`` in place; False if the user is gone."""
    async with db.session_scope() as session:
        user = await session.get(User, user_id)
        if user is None:
            return False
        user.password_hash = new_hash
        session.add(user)
        return True


def _mailer_configured(settings) -> bool:  # noqa: ANN001 - Settings is frozen
    """Whether an outbound mailer is wired. No mailer yet ⇒ dev returns tokens."""
    return bool(getattr(settings, "smtp_host", "") or getattr(settings, "mailer_url", ""))


# --- request/response models ------------------------------------------------
class EmailIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)


class ResetIn(BaseModel):
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=_MIN_PASSWORD, max_length=1024)


class TokenIn(BaseModel):
    token: str = Field(..., min_length=1)


# --- password reset ---------------------------------------------------------
@router.post("/request-password-reset")
async def request_password_reset(body: EmailIn, request: Request) -> dict:
    """Always 200. Issues a reset token for the email; in dev returns it inline."""
    store = request.app.state.store
    settings = request.app.state.settings
    email = body.email.strip().lower()

    user = await store.get_user_by_email(email)
    # Mint a token either way: real sub for a real user, opaque sub otherwise so
    # the response shape (and timing profile) does not reveal existence.
    subject = user.id if user is not None else uuid.uuid4().hex
    token = _issue_purpose_token(
        subject, settings.session_secret, _TYP_PWRESET, _RESET_TTL_MINUTES
    )

    resp: dict = {"ok": True, "message": _RESET_MESSAGE}
    if not _mailer_configured(settings):
        resp["reset_token"] = token  # dev only; prod emails this instead
    return resp


@router.post("/reset-password")
async def reset_password(body: ResetIn, request: Request) -> dict:
    """Verify a ``pwreset`` token and set the new password. 400 on bad token."""
    store = request.app.state.store
    settings = request.app.state.settings
    user_id = _decode_purpose_token(
        body.token, settings.session_secret, _TYP_PWRESET
    )
    ok = await _set_password_hash(user_id, hash_password(body.new_password))
    if not ok:
        # Token was well-formed but the subject no longer exists (or never did,
        # e.g. an unknown-email token). Same generic error — no enumeration.
        raise HTTPException(status_code=400, detail=_BAD_TOKEN)
    _ = store  # store kept in signature parity with the rest of the module
    return {"ok": True, "message": "Your password has been updated."}


# --- email verification -----------------------------------------------------
@router.post("/request-verify")
async def request_verify(body: EmailIn, request: Request) -> dict:
    """Always 200. Issues a verification token; in dev returns it inline."""
    store = request.app.state.store
    settings = request.app.state.settings
    email = body.email.strip().lower()

    user = await store.get_user_by_email(email)
    subject = user.id if user is not None else uuid.uuid4().hex
    token = _issue_purpose_token(
        subject, settings.session_secret, _TYP_VERIFY, _VERIFY_TTL_MINUTES
    )

    resp: dict = {"ok": True, "message": _VERIFY_MESSAGE}
    if not _mailer_configured(settings):
        resp["verify_token"] = token
    return resp


@router.post("/verify-email")
async def verify_email(body: TokenIn, request: Request) -> dict:
    """Verify a ``verify`` token. Stateless ack (schema has no verified flag)."""
    store = request.app.state.store
    settings = request.app.state.settings
    user_id = _decode_purpose_token(
        body.token, settings.session_secret, _TYP_VERIFY
    )
    user = await store.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=400, detail=_BAD_TOKEN)
    return {"ok": True, "verified": True, "user_id": user.id}


__all__ = ["router"]
