"""Entitlement guards — the frozen tier math (billing/entitlements.py).

This module is fully implemented + FROZEN, so nothing here is xfailed: these are
the boundary contracts every other billing surface leans on.
"""

from __future__ import annotations

import pytest

from ghostpanel.billing.entitlements import (
    TIER_LIMITS,
    Entitlements,
    QuotaExceeded,
    check_can_add_flow,
    check_can_add_seat,
    check_can_enqueue,
    entitlements_for,
)
from ghostpanel.store.models import Tier


# --------------------------------------------------------------------------- #
# TIER_LIMITS sanity
# --------------------------------------------------------------------------- #
def test_all_tiers_present_and_typed():
    for tier in (Tier.FREE, Tier.TEAM, Tier.AUDIT):
        ent = TIER_LIMITS[tier]
        assert isinstance(ent, Entitlements)
        assert ent.tier is tier
        assert isinstance(ent.label, str) and ent.label


def test_free_is_the_most_restrictive_public_tier():
    free = TIER_LIMITS[Tier.FREE]
    assert free.private_repos is False
    assert free.max_flows == 1
    assert free.max_runs_per_month == 100
    assert free.max_seats == 1


def test_team_is_strictly_more_generous_than_free():
    free, team = TIER_LIMITS[Tier.FREE], TIER_LIMITS[Tier.TEAM]
    assert team.private_repos is True
    assert team.max_flows > free.max_flows
    assert team.max_runs_per_month > free.max_runs_per_month
    assert team.max_seats > free.max_seats


def test_audit_is_unlimited():
    audit = TIER_LIMITS[Tier.AUDIT]
    assert audit.max_flows == -1
    assert audit.max_runs_per_month == -1
    assert audit.max_seats == -1
    assert audit.private_repos is True


def test_entitlements_for_maps_tier_and_defaults_to_free():
    assert entitlements_for(Tier.TEAM) is TIER_LIMITS[Tier.TEAM]
    # Any unknown value falls back to Free (defensive default).
    assert entitlements_for("nonsense") is TIER_LIMITS[Tier.FREE]  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# check_can_enqueue — monthly run quota (count = runs_this_period + 1)
# --------------------------------------------------------------------------- #
def test_enqueue_free_one_below_limit_passes():
    # 99 used -> the 100th run is still within the 100/month cap.
    check_can_enqueue(Tier.FREE, 99)


def test_enqueue_free_at_limit_raises():
    # 100 used -> the 101st run exceeds the cap.
    with pytest.raises(QuotaExceeded):
        check_can_enqueue(Tier.FREE, 100)


def test_enqueue_team_allows_far_more_than_free():
    check_can_enqueue(Tier.TEAM, 100)      # trivially fine
    check_can_enqueue(Tier.TEAM, 1999)     # last allowed under 2000
    with pytest.raises(QuotaExceeded):
        check_can_enqueue(Tier.TEAM, 2000)


def test_enqueue_audit_is_unlimited():
    check_can_enqueue(Tier.AUDIT, 10_000_000)


# --------------------------------------------------------------------------- #
# check_can_add_seat — seat quota (count = current_seats + 1)
# --------------------------------------------------------------------------- #
def test_add_seat_free_one_below_limit_passes():
    check_can_add_seat(Tier.FREE, 0)       # first seat (the owner)


def test_add_seat_free_at_limit_raises():
    # Free = 1 seat: with the owner already occupying it, no teammate fits.
    with pytest.raises(QuotaExceeded):
        check_can_add_seat(Tier.FREE, 1)


def test_add_seat_team_higher_ceiling():
    check_can_add_seat(Tier.TEAM, 1)
    check_can_add_seat(Tier.TEAM, 9)       # 10th seat allowed
    with pytest.raises(QuotaExceeded):
        check_can_add_seat(Tier.TEAM, 10)


def test_add_seat_audit_is_unlimited():
    check_can_add_seat(Tier.AUDIT, 10_000_000)


# --------------------------------------------------------------------------- #
# check_can_add_flow — flow quota (count = current_flows + 1)
# --------------------------------------------------------------------------- #
def test_add_flow_free_one_below_limit_passes():
    check_can_add_flow(Tier.FREE, 0)       # first flow


def test_add_flow_free_at_limit_raises():
    with pytest.raises(QuotaExceeded):
        check_can_add_flow(Tier.FREE, 1)


def test_add_flow_team_higher_ceiling():
    check_can_add_flow(Tier.TEAM, 9)       # 10th flow allowed
    with pytest.raises(QuotaExceeded):
        check_can_add_flow(Tier.TEAM, 10)


def test_add_flow_audit_is_unlimited():
    check_can_add_flow(Tier.AUDIT, 10_000_000)


def test_quota_exceeded_message_is_actionable():
    """The API surfaces this message verbatim as the 402 body — keep it human."""
    try:
        check_can_add_seat(Tier.FREE, 1)
    except QuotaExceeded as exc:
        assert "Free" in str(exc)
        assert "Upgrade" in str(exc)
    else:  # pragma: no cover
        pytest.fail("expected QuotaExceeded")
