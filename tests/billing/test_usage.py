"""Usage + membership queries (billing/usage.py, P4-A).

Real temp-SQLite DB (``db_engine`` fixture) seeded via the frozen Store + direct
model inserts. The whole module xfails (strict=False) while usage.py is a stub, so
it flips to real coverage the moment P4-A lands. ``usage._now`` is tz-aware, so we
seed tz-aware ``created_at`` values.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from ghostpanel.billing import usage
from ghostpanel.store import db
from ghostpanel.store.models import RunRow, RunState, Tier, User, _uuid
from ghostpanel.store.repo import Store

from .conftest import is_stub

pytestmark = pytest.mark.xfail(
    is_stub(usage.runs_this_period),
    reason="billing/usage.py still a stub (P4-A not landed)",
    strict=False,
)

UTC = _dt.timezone.utc


# --------------------------------------------------------------------------- #
# seed helpers
# --------------------------------------------------------------------------- #
async def _seed_owner_and_project(name: str = "Acme", email: str = "owner@example.com"):
    store = Store()
    owner = await store.create_user(email, "hash")
    project = await store.create_project(owner=owner, name=name)
    return store, owner, project


async def _add_run(project_id: str, created_at: _dt.datetime, *, state=RunState.FINISHED):
    async with db.session_scope() as session:
        session.add(
            RunRow(
                id=_uuid(),
                project_id=project_id,
                state=state,
                created_at=created_at,
            )
        )


# --------------------------------------------------------------------------- #
# runs_this_period
# --------------------------------------------------------------------------- #
async def test_runs_this_period_counts_since_explicit_cutoff(db_engine):
    _store, _owner, project = await _seed_owner_and_project()
    cutoff = _dt.datetime(2026, 7, 1, tzinfo=UTC)
    # Two after the cutoff, one before -> only the two count.
    await _add_run(project.id, _dt.datetime(2026, 7, 5, tzinfo=UTC))
    await _add_run(project.id, _dt.datetime(2026, 7, 20, tzinfo=UTC))
    await _add_run(project.id, _dt.datetime(2026, 6, 15, tzinfo=UTC))

    assert await usage.runs_this_period(project.id, since=cutoff) == 2


async def test_runs_this_period_default_is_current_month(db_engine):
    _store, _owner, project = await _seed_owner_and_project()
    now = _dt.datetime.now(UTC)
    await _add_run(project.id, now)
    await _add_run(project.id, now - _dt.timedelta(hours=1))
    # ~45 days ago is unambiguously a previous month -> excluded.
    await _add_run(project.id, now - _dt.timedelta(days=45))

    assert await usage.runs_this_period(project.id) == 2


async def test_runs_this_period_is_scoped_to_project(db_engine):
    _store, _owner, project = await _seed_owner_and_project()
    _store2, _owner2, other = await _seed_owner_and_project(
        name="Other", email="owner2@example.com"
    )
    now = _dt.datetime.now(UTC)
    await _add_run(project.id, now)
    await _add_run(other.id, now)
    await _add_run(other.id, now)

    assert await usage.runs_this_period(project.id) == 1
    assert await usage.runs_this_period(other.id) == 2


async def test_runs_this_period_zero_when_none(db_engine):
    _store, _owner, project = await _seed_owner_and_project()
    assert await usage.runs_this_period(project.id) == 0


# --------------------------------------------------------------------------- #
# member_count / list_members
# --------------------------------------------------------------------------- #
async def test_member_count_starts_at_one_for_owner(db_engine):
    _store, _owner, project = await _seed_owner_and_project()
    assert await usage.member_count(project.id) == 1


async def test_list_members_shape_includes_owner(db_engine):
    _store, owner, project = await _seed_owner_and_project()
    members = await usage.list_members(project.id)
    assert isinstance(members, list) and len(members) == 1
    m = members[0]
    assert m.user_id == owner.id
    assert m.email == "owner@example.com"
    assert m.role == "owner"


# --------------------------------------------------------------------------- #
# add_member_by_email / remove_member
# --------------------------------------------------------------------------- #
async def test_add_member_by_email_happy_path(db_engine):
    store, _owner, project = await _seed_owner_and_project()
    await store.create_user("teammate@example.com", "hash")

    info = await usage.add_member_by_email(project.id, "teammate@example.com")
    assert info.email == "teammate@example.com"
    assert info.role == "member"
    assert await usage.member_count(project.id) == 2

    emails = {m.email for m in await usage.list_members(project.id)}
    assert emails == {"owner@example.com", "teammate@example.com"}


async def test_add_member_unknown_email_raises_lookup_error(db_engine):
    _store, _owner, project = await _seed_owner_and_project()
    with pytest.raises(LookupError):
        await usage.add_member_by_email(project.id, "ghost@example.com")


async def test_add_member_duplicate_raises_value_error(db_engine):
    store, _owner, project = await _seed_owner_and_project()
    await store.create_user("teammate@example.com", "hash")
    await usage.add_member_by_email(project.id, "teammate@example.com")

    with pytest.raises(ValueError):
        await usage.add_member_by_email(project.id, "teammate@example.com")


async def test_remove_member_refuses_owner(db_engine):
    _store, owner, project = await _seed_owner_and_project()
    assert await usage.remove_member(project.id, owner.id) is False
    assert await usage.member_count(project.id) == 1


async def test_remove_member_removes_a_teammate(db_engine):
    store, _owner, project = await _seed_owner_and_project()
    teammate: User = await store.create_user("teammate@example.com", "hash")
    await usage.add_member_by_email(project.id, "teammate@example.com")
    assert await usage.member_count(project.id) == 2

    assert await usage.remove_member(project.id, teammate.id) is True
    assert await usage.member_count(project.id) == 1


# --------------------------------------------------------------------------- #
# set_project_billing
# --------------------------------------------------------------------------- #
async def test_set_project_billing_flips_tier_and_flags(db_engine):
    store, _owner, project = await _seed_owner_and_project()
    assert project.tier == Tier.FREE
    assert project.private_repos_enabled is False

    await usage.set_project_billing(
        project.id,
        tier="team",
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_456",
        private_repos_enabled=True,
    )

    updated = await store.get_project(project.id)
    assert updated.tier == Tier.TEAM
    assert updated.private_repos_enabled is True
    assert updated.stripe_customer_id == "cus_123"
    assert updated.stripe_subscription_id == "sub_456"


async def test_set_project_billing_downgrade_to_free(db_engine):
    store, _owner, project = await _seed_owner_and_project()
    await usage.set_project_billing(
        project.id, tier="team", stripe_customer_id="cus_1",
        stripe_subscription_id="sub_1", private_repos_enabled=True,
    )
    await usage.set_project_billing(
        project.id, tier="free", private_repos_enabled=False,
    )

    updated = await store.get_project(project.id)
    assert updated.tier == Tier.FREE
    assert updated.private_repos_enabled is False
