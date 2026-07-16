"""Session tokens (JWT via PyJWT). STUB — Agent P2-C. Signatures FROZEN."""

from __future__ import annotations

import datetime as _dt

import jwt

_ALGO = "HS256"


class InvalidToken(Exception):
    """Raised when a session token is missing/expired/tampered."""


def issue_session_token(user_id: str, secret: str, *, ttl_hours: int = 720) -> str:
    """HS256 JWT with sub=user_id, iat, exp=now+ttl. Raise ValueError on empty secret."""
    if not secret:
        raise ValueError("session secret must not be empty")
    now = _dt.datetime.now(_dt.timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + _dt.timedelta(hours=ttl_hours),
    }
    return jwt.encode(payload, secret, algorithm=_ALGO)


def decode_session_token(token: str, secret: str) -> str:
    """Verify signature + expiry; return the user_id (sub). Raise InvalidToken otherwise."""
    if not secret:
        raise InvalidToken("session secret must not be empty")
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGO])
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise InvalidToken("token has no subject")
    return sub


__all__ = ["InvalidToken", "issue_session_token", "decode_session_token"]
