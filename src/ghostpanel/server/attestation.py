"""Authorization attestation for run creation.

The product points an autonomous browser-agent swarm at a live website. Before a
run may be created the caller MUST attest that they own the target site or have
explicit permission to run automated tests against it. This is a hard,
server-side gate — never trust the frontend alone.

Both run-creation surfaces use this module:
  * ``server.api`` (the public demo ``POST /runs``)
  * ``server.routers.runs`` (the hosted, billed ``POST /v2/runs``)

``require_attestation`` raises ``HTTPException(403)`` when the attestation is
missing/false, otherwise it returns an audit record (who / when / which domain)
suitable for persisting alongside the run for an audit trail.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import HTTPException

# The exact copy the frontend checkbox shows — kept here so the server error and
# the UI stay in sync.
ATTESTATION_STATEMENT = (
    "I confirm I own this website or have explicit permission to run automated "
    "tests against it."
)


def target_domain(url: str) -> str:
    """Best-effort registrable host for the target URL (audit + UI copy).

    Never raises — a malformed URL falls back to the raw string so the audit
    record is still populated; URL *safety* is enforced separately by the SSRF
    guard.
    """
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        host = ""
    return host or url.strip()


def require_attestation(
    authorized: bool,
    url: str,
    *,
    subject: Optional[str] = None,
) -> dict[str, Any]:
    """Enforce the ownership attestation.

    Raises ``HTTPException(403)`` if ``authorized`` is not truthy. Otherwise
    returns an audit record to persist with the run::

        {authorized, authorized_by, authorized_at, authorized_domain, statement}

    ``subject`` is the attesting principal (a project id, user email, or similar);
    ``None`` for the unauthenticated public demo.
    """
    if not authorized:
        raise HTTPException(
            status_code=403,
            detail=(
                "Authorization required: you must confirm you own the target "
                "website or have explicit permission to run automated tests "
                "against it before starting a run."
            ),
        )
    return {
        "authorized": True,
        "authorized_by": subject or "anonymous",
        "authorized_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "authorized_domain": target_domain(url),
        "statement": ATTESTATION_STATEMENT,
    }


__all__ = ["ATTESTATION_STATEMENT", "target_domain", "require_attestation"]
