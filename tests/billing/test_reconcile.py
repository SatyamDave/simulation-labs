"""Billing reconciliation — W1-D.

Real temp-SQLite DB (the ``db_engine`` fixture from ``tests/billing/conftest.py``),
Stripe reached only through ``reconcile._subscription_status`` which we monkeypatch,
so nothing touches the network.
"""

from __future__ import annotations

from dataclasses import dataclass

from ghostpanel.billing import reconcile
from ghostpanel.store import db
from ghostpanel.store.models import Project, Tier
from ghostpanel.store.repo import Store


@dataclass
class FakeSettings:
    """Minimal stand-in for server config Settings (only what reconcile reads)."""
    stripe_secret_key: str = "sk_test_123"


async def _seed_project(
    *,
    tier: Tier = Tier.FREE,
    private_repos: bool = False,
    sub_id: str = "sub_1",
    email: str = "owner@example.com",
) -> Project:
    store = Store()
    owner = await store.create_user(email, "hash")
    project = await store.create_project(owner=owner, name="Acme", tier=tier)
    # Set the drift-relevant fields directly on the row.
    async with db.session_scope() as session:
        row = await session.get(Project, project.id)
        row.private_repos_enabled = private_repos
        row.stripe_subscription_id = sub_id
        row.stripe_customer_id = "cus_1"
        session.add(row)
    return project


def _patch_status(monkeypatch, status: str):
    seen: dict = {}

    def _fake(secret: str, sub_id: str) -> str:
        seen["secret"] = secret
        seen["sub_id"] = sub_id
        return status

    monkeypatch.setattr(reconcile, "_subscription_status", _fake)
    return seen


async def _tier_of(project_id: str) -> tuple[Tier, bool]:
    async with db.session_scope() as session:
        row = await session.get(Project, project_id)
        return row.tier, row.private_repos_enabled


# --------------------------------------------------------------------------- #
# drift correction
# --------------------------------------------------------------------------- #
async def test_team_but_canceled_downgrades_to_free(db_engine, monkeypatch):
    project = await _seed_project(tier=Tier.TEAM, private_repos=True)
    _patch_status(monkeypatch, "canceled")

    res = await reconcile.reconcile_project(project.id, FakeSettings())

    assert res["changed"] is True
    assert res["reason"] == reconcile.REASON_CORRECTED
    assert res["before"] == {"tier": "team", "private_repos": True}
    assert res["after"] == {"tier": "free", "private_repos": False}
    assert await _tier_of(project.id) == (Tier.FREE, False)


async def test_free_but_active_upgrades_to_team(db_engine, monkeypatch):
    project = await _seed_project(tier=Tier.FREE, private_repos=False)
    _patch_status(monkeypatch, "active")

    res = await reconcile.reconcile_project(project.id, FakeSettings())

    assert res["changed"] is True
    assert res["after"] == {"tier": "team", "private_repos": True}
    assert await _tier_of(project.id) == (Tier.TEAM, True)


async def test_unpaid_downgrades_to_free(db_engine, monkeypatch):
    project = await _seed_project(tier=Tier.TEAM, private_repos=True)
    _patch_status(monkeypatch, "unpaid")

    res = await reconcile.reconcile_project(project.id, FakeSettings())
    assert res["changed"] is True
    assert await _tier_of(project.id) == (Tier.FREE, False)


# --------------------------------------------------------------------------- #
# in-sync / idempotency
# --------------------------------------------------------------------------- #
async def test_in_sync_team_active_no_change(db_engine, monkeypatch):
    project = await _seed_project(tier=Tier.TEAM, private_repos=True)
    _patch_status(monkeypatch, "active")

    res = await reconcile.reconcile_project(project.id, FakeSettings())

    assert res["changed"] is False
    assert res["reason"] == reconcile.REASON_IN_SYNC
    assert await _tier_of(project.id) == (Tier.TEAM, True)


async def test_rerun_is_idempotent(db_engine, monkeypatch):
    project = await _seed_project(tier=Tier.TEAM, private_repos=True)
    _patch_status(monkeypatch, "canceled")

    first = await reconcile.reconcile_project(project.id, FakeSettings())
    second = await reconcile.reconcile_project(project.id, FakeSettings())

    assert first["changed"] is True
    assert second["changed"] is False
    assert second["reason"] == reconcile.REASON_IN_SYNC
    assert await _tier_of(project.id) == (Tier.FREE, False)


async def test_passes_secret_and_sub_id_to_stripe(db_engine, monkeypatch):
    project = await _seed_project(tier=Tier.FREE, sub_id="sub_xyz")
    seen = _patch_status(monkeypatch, "canceled")

    await reconcile.reconcile_project(project.id, FakeSettings(stripe_secret_key="sk_live_9"))

    assert seen == {"secret": "sk_live_9", "sub_id": "sub_xyz"}


# --------------------------------------------------------------------------- #
# no-op paths
# --------------------------------------------------------------------------- #
async def test_unconfigured_stripe_is_noop(db_engine, monkeypatch):
    project = await _seed_project(tier=Tier.TEAM, private_repos=True)

    def _boom(secret, sub_id):  # must never be called
        raise AssertionError("Stripe should not be consulted when unconfigured")

    monkeypatch.setattr(reconcile, "_subscription_status", _boom)

    res = await reconcile.reconcile_project(project.id, FakeSettings(stripe_secret_key=""))

    assert res["changed"] is False
    assert res["reason"] == reconcile.REASON_NOT_CONFIGURED
    assert await _tier_of(project.id) == (Tier.TEAM, True)  # untouched


async def test_no_subscription_id_is_noop(db_engine, monkeypatch):
    project = await _seed_project(tier=Tier.TEAM, private_repos=True, sub_id="")

    def _boom(secret, sub_id):
        raise AssertionError("Stripe should not be consulted without a subscription id")

    monkeypatch.setattr(reconcile, "_subscription_status", _boom)

    res = await reconcile.reconcile_project(project.id, FakeSettings())

    assert res["changed"] is False
    assert res["reason"] == reconcile.REASON_NO_SUBSCRIPTION


async def test_unknown_project_is_noop(db_engine, monkeypatch):
    _patch_status(monkeypatch, "active")
    res = await reconcile.reconcile_project("does-not-exist", FakeSettings())
    assert res["changed"] is False
    assert res["reason"] == reconcile.REASON_NOT_FOUND
    assert res["before"] is None


async def test_transient_status_left_untouched(db_engine, monkeypatch):
    project = await _seed_project(tier=Tier.TEAM, private_repos=True)
    _patch_status(monkeypatch, "past_due")

    res = await reconcile.reconcile_project(project.id, FakeSettings())

    assert res["changed"] is False
    assert res["reason"] == reconcile.REASON_UNHANDLED_STATUS
    assert await _tier_of(project.id) == (Tier.TEAM, True)


# --------------------------------------------------------------------------- #
# reconcile_all
# --------------------------------------------------------------------------- #
async def test_reconcile_all_only_visits_subscribed_projects(db_engine, monkeypatch):
    store = Store()
    o1 = await store.create_user("a@x.com", "h")
    p_sub = await store.create_project(owner=o1, name="HasSub", tier=Tier.TEAM)
    async with db.session_scope() as session:
        row = await session.get(Project, p_sub.id)
        row.stripe_subscription_id = "sub_a"
        row.private_repos_enabled = True
        session.add(row)
    # A second project with no subscription id — must be skipped entirely.
    o2 = await store.create_user("b@x.com", "h")
    await store.create_project(owner=o2, name="NoSub", tier=Tier.FREE)

    _patch_status(monkeypatch, "canceled")
    results = await reconcile.reconcile_all(FakeSettings())

    assert len(results) == 1
    assert results[0]["project_id"] == p_sub.id
    assert results[0]["changed"] is True
    assert await _tier_of(p_sub.id) == (Tier.FREE, False)


async def test_reconcile_all_noop_when_unconfigured(db_engine):
    await _seed_project(tier=Tier.TEAM, private_repos=True)
    assert await reconcile.reconcile_all(FakeSettings(stripe_secret_key="")) == []
