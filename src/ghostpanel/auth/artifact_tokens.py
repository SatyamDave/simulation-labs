"""Short-lived HMAC-signed tokens for artifact URLs.

Artifacts (report.html, .webm, .wav) are tenant data, so they are NOT served from
an open static mount. They go through an authed route that either (a) accepts a
session/API-key principal scoped to the run, or (b) accepts a signed token — so
`<img>`/`<video>` tags (which can't send an Authorization header) can still load
them via a URL. Tokens are HMAC(run_id:rel_path:exp) with the server session secret
and expire quickly.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time


def _sig(run_id: str, rel_path: str, exp: int, secret: str) -> str:
    msg = f"{run_id}:{rel_path}:{exp}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def sign_artifact(run_id: str, rel_path: str, secret: str, *, ttl_s: int = 3600) -> str:
    """Return a `<exp>.<sig>` token authorizing GET of one artifact for ttl_s seconds."""
    if not secret:
        raise ValueError("cannot sign artifact tokens without a secret")
    exp = int(time.time()) + ttl_s
    return f"{exp}.{_sig(run_id, rel_path, exp, secret)}"


def verify_artifact(run_id: str, rel_path: str, token: str, secret: str) -> bool:
    """True iff `token` is a valid, unexpired signature for (run_id, rel_path).
    Never raises."""
    try:
        exp_str, sig = token.split(".", 1)
        exp = int(exp_str)
    except (ValueError, AttributeError):
        return False
    if exp < int(time.time()):
        return False
    expected = _sig(run_id, rel_path, exp, secret)
    return hmac.compare_digest(expected, sig)


__all__ = ["sign_artifact", "verify_artifact"]
