"""Tier entitlements — the single source of truth for what each plan allows.
FROZEN. Billing, the API, and the dashboard all read from TIER_LIMITS.

Limits use -1 for "unlimited". These map to the landing-page pricing:
Free ($0, public repos, 1 flow), Team ($49/seat·mo, private repos + more flows),
Audit (manual/custom).
"""

from __future__ import annotations

from dataclasses import dataclass

from ghostpanel.store.models import Tier


@dataclass(frozen=True)
class Entitlements:
    tier: Tier
    label: str
    price_display: str
    max_flows: int              # -1 = unlimited
    max_runs_per_month: int     # -1 = unlimited
    max_seats: int              # -1 = unlimited
    private_repos: bool


TIER_LIMITS: dict[Tier, Entitlements] = {
    Tier.FREE: Entitlements(
        tier=Tier.FREE, label="Free", price_display="$0",
        max_flows=1, max_runs_per_month=100, max_seats=1, private_repos=False,
    ),
    Tier.TEAM: Entitlements(
        tier=Tier.TEAM, label="Team", price_display="$49 / seat · mo",
        max_flows=10, max_runs_per_month=2000, max_seats=10, private_repos=True,
    ),
    Tier.AUDIT: Entitlements(
        tier=Tier.AUDIT, label="Audit", price_display="custom",
        max_flows=-1, max_runs_per_month=-1, max_seats=-1, private_repos=True,
    ),
}


class QuotaExceeded(Exception):
    """Raised when an action would exceed the project's tier entitlements.

    The API maps this to HTTP 402 (Payment Required) with the message, so the
    dashboard can prompt an upgrade.
    """


def entitlements_for(tier: Tier) -> Entitlements:
    return TIER_LIMITS.get(tier, TIER_LIMITS[Tier.FREE])


def _within(limit: int, count: int) -> bool:
    """True if `count` (the value AFTER the action) is allowed under `limit`."""
    return limit < 0 or count <= limit


def check_can_enqueue(tier: Tier, runs_this_period: int) -> None:
    """Raise QuotaExceeded if a new run would exceed the monthly run quota."""
    ent = entitlements_for(tier)
    if not _within(ent.max_runs_per_month, runs_this_period + 1):
        raise QuotaExceeded(
            f"{ent.label} plan allows {ent.max_runs_per_month} runs/month "
            f"(used {runs_this_period}). Upgrade for more."
        )


def check_can_add_seat(tier: Tier, current_seats: int) -> None:
    """Raise QuotaExceeded if adding a member would exceed the seat limit."""
    ent = entitlements_for(tier)
    if not _within(ent.max_seats, current_seats + 1):
        raise QuotaExceeded(
            f"{ent.label} plan allows {ent.max_seats} seat(s) "
            f"(using {current_seats}). Upgrade to add teammates."
        )


def check_can_add_flow(tier: Tier, current_flows: int) -> None:
    """Raise QuotaExceeded if adding a flow would exceed the flow limit."""
    ent = entitlements_for(tier)
    if not _within(ent.max_flows, current_flows + 1):
        raise QuotaExceeded(
            f"{ent.label} plan allows {ent.max_flows} flow(s). Upgrade for more."
        )


__all__ = [
    "Entitlements", "TIER_LIMITS", "QuotaExceeded",
    "entitlements_for", "check_can_enqueue", "check_can_add_seat", "check_can_add_flow",
]
