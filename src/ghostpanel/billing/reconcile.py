"""Billing reconciliation — W1-D (billing correctness).

Webhooks are the primary path that keeps a project's tier in sync with its Stripe
subscription, but webhooks can be missed (endpoint down, event dropped, a manual
change in the Stripe dashboard). Reconciliation is the *backstop*: it re-derives
the correct tier from Stripe's own view of the subscription and corrects any drift.

Contract
--------
``reconcile_project(project_id, settings) -> dict`` returns::

    {
        "project_id": <str>,
        "before":     {"tier": <str>, "private_repos": <bool>} | None,
        "after":      {"tier": <str>, "private_repos": <bool>} | None,
        "changed":    <bool>,
        "reason":     <str>,   # why we did / didn't act (see REASON_* below)
    }

It is **idempotent**: applying it to an already-correct project makes no write and
reports ``changed=False``. It is a clean **no-op** when Stripe is unconfigured, the
project is unknown, or the project has no ``stripe_subscription_id``.

Stripe is reached only through ``_subscription_status`` — a thin, monkeypatchable
wrapper around ``stripe.Subscription.retrieve`` so tests never touch the network and
so we do not have to edit the frozen ``stripe_client`` module.
"""

from __future__ import annotations

from typing import Any, Optional

import stripe

from ghostpanel.billing import usage
from ghostpanel.store import db
from ghostpanel.store.models import Project, Tier
from sqlmodel import select

# Subscription statuses that grant paid (Team) access.
ACTIVE_STATUSES = frozenset({"active", "trialing"})
# Statuses that revoke paid access → downgrade to Free.
INACTIVE_STATUSES = frozenset(
    {"canceled", "unpaid", "incomplete_expired", "none", ""}
)
# Everything else (e.g. "past_due", "incomplete", "paused") is a transient dunning
# / setup state: we deliberately leave the tier untouched and let Stripe's dunning
# resolve it to a terminal status, which a later reconcile run will act on.

# Machine-readable reasons for the returned dict (handy for ops dashboards/logs).
REASON_NOT_CONFIGURED = "stripe_not_configured"
REASON_NOT_FOUND = "project_not_found"
REASON_NO_SUBSCRIPTION = "no_subscription_id"
REASON_IN_SYNC = "in_sync"
REASON_CORRECTED = "corrected"
REASON_UNHANDLED_STATUS = "unhandled_status"


def _subscription_status(secret: str, sub_id: str) -> str:
    """Return the Stripe subscription's ``status`` string.

    Thin wrapper around ``stripe.Subscription.retrieve`` so the reconcile logic has
    a single, monkeypatchable seam (tests replace this function). Sets ``api_key``
    locally rather than relying on process-global mutable state — same discipline as
    ``billing.stripe_client``.
    """
    stripe.api_key = secret
    sub = stripe.Subscription.retrieve(sub_id)
    # Stripe objects behave like dicts; support both attribute and mapping access.
    status = getattr(sub, "status", None)
    if status is None and isinstance(sub, dict):
        status = sub.get("status")
    return status or ""


def _snapshot(project: Project) -> dict[str, Any]:
    return {"tier": project.tier.value, "private_repos": project.private_repos_enabled}


def _stripe_configured(settings: Any) -> bool:
    """True when a Stripe secret key is present on settings."""
    secret = getattr(settings, "stripe_secret_key", "") or ""
    return bool(secret.strip())


def _desired_state(status: str) -> Optional[tuple[str, bool]]:
    """Map a subscription status to (tier, private_repos), or None if we should
    leave the project untouched (transient/unknown status)."""
    if status in ACTIVE_STATUSES:
        return (Tier.TEAM.value, True)
    if status in INACTIVE_STATUSES:
        return (Tier.FREE.value, False)
    return None


async def reconcile_project(project_id: str, settings: Any) -> dict:
    """Correct one project's tier to match its Stripe subscription. Idempotent."""
    async with db.session_scope() as session:
        project = await session.get(Project, project_id)
        before = _snapshot(project) if project is not None else None

    result: dict[str, Any] = {
        "project_id": project_id,
        "before": before,
        "after": before,
        "changed": False,
        "reason": "",
    }

    if not _stripe_configured(settings):
        result["reason"] = REASON_NOT_CONFIGURED
        return result

    if project is None:
        result["reason"] = REASON_NOT_FOUND
        return result

    sub_id = (project.stripe_subscription_id or "").strip()
    if not sub_id:
        result["reason"] = REASON_NO_SUBSCRIPTION
        return result

    status = _subscription_status(settings.stripe_secret_key, sub_id)
    desired = _desired_state(status)
    if desired is None:
        result["reason"] = REASON_UNHANDLED_STATUS
        return result

    desired_tier, desired_private = desired
    if (before["tier"], before["private_repos"]) == (desired_tier, desired_private):
        result["reason"] = REASON_IN_SYNC
        return result

    await usage.set_project_billing(
        project_id,
        tier=desired_tier,
        private_repos_enabled=desired_private,
    )
    result["after"] = {"tier": desired_tier, "private_repos": desired_private}
    result["changed"] = True
    result["reason"] = REASON_CORRECTED
    return result


async def reconcile_all(settings: Any) -> list[dict]:
    """Reconcile every project that carries a Stripe subscription id.

    No-op (empty list) when Stripe is unconfigured. Safe to run on a schedule; each
    project is independently idempotent.
    """
    if not _stripe_configured(settings):
        return []

    async with db.session_scope() as session:
        rows = await session.exec(
            select(Project).where(Project.stripe_subscription_id != "")
        )
        project_ids = [p.id for p in rows.all()]

    return [await reconcile_project(pid, settings) for pid in project_ids]


__all__ = [
    "reconcile_project",
    "reconcile_all",
    "ACTIVE_STATUSES",
    "INACTIVE_STATUSES",
]
