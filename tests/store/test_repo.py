"""Store (P2-A) data-access tests — offline, SQLite temp file per test.

The Store is fully implemented, so these are expected to PASS. Every method opens
its own ``session_scope`` against the process-global engine installed by the
``db_engine`` fixture (see conftest).
"""

from __future__ import annotations

import asyncio

import pytest

from ghostpanel_contracts import RunReport
from ghostpanel.store.models import Role, RunState
from ghostpanel.store.repo import Store


def _report(run_id: str, rate: float) -> RunReport:
    return RunReport(
        run_id=run_id,
        target_url="https://example.com/signup",
        task="sign up for an account",
        completion_rate=rate,
    )


async def _make_project(store: Store, email: str = "owner@example.com"):
    user = await store.create_user(email, "hash")
    project = await store.create_project(owner=user, name="Acme")
    return user, project


async def test_user_create_get_by_email(db_engine):
    store = Store()
    user = await store.create_user("alice@example.com", "hashed-pw")
    assert user.id

    fetched = await store.get_user(user.id)
    assert fetched is not None and fetched.email == "alice@example.com"

    by_email = await store.get_user_by_email("alice@example.com")
    assert by_email is not None and by_email.id == user.id

    assert await store.get_user_by_email("nobody@example.com") is None


async def test_user_email_is_unique(db_engine):
    store = Store()
    await store.create_user("dup@example.com", "h1")
    with pytest.raises(Exception):
        # UNIQUE(email) violation surfaces as an IntegrityError after flush.
        await store.create_user("dup@example.com", "h2")


async def test_create_project_makes_owner_membership(db_engine):
    store = Store()
    user, project = await _make_project(store)

    role = await store.member_role(user.id, project.id)
    assert role == Role.OWNER

    projects = await store.list_projects_for_user(user.id)
    assert [p.id for p in projects] == [project.id]


async def test_api_key_roundtrip_valid_bogus_revoked(db_engine):
    store = Store()
    _user, project = await _make_project(store)

    row, plaintext = await store.create_api_key(project.id, name="ci")
    assert plaintext.startswith("sl_live_")

    # Valid key resolves the owning project.
    resolved = await store.project_for_api_key(plaintext)
    assert resolved is not None and resolved.id == project.id

    # Bogus key resolves to nothing.
    assert await store.project_for_api_key("sl_live_deadbeef_notarealsecret") is None

    # Revoked key stops resolving.
    assert await store.revoke_api_key(row.id, project.id) is True
    assert await store.project_for_api_key(plaintext) is None


async def test_create_run_then_set_run_report_promotes_fields(db_engine):
    store = Store()
    _user, project = await _make_project(store)

    await store.create_run(
        run_id="run-1",
        project_id=project.id,
        target_url="https://example.com/signup",
        task="sign up",
        persona_ids=["grandma-72"],
        flow_name="signup",
    )
    before = await store.get_run("run-1")
    assert before.state == RunState.QUEUED
    assert before.completion_rate is None

    await store.set_run_report("run-1", _report("run-1", 0.6))

    after = await store.get_run("run-1")
    assert after.state == RunState.FINISHED
    assert after.completion_rate == 0.6
    assert after.finished_at is not None
    assert after.report_json is not None and after.report_json["run_id"] == "run-1"


async def test_list_runs_filters_by_flow(db_engine):
    store = Store()
    _user, project = await _make_project(store)

    await store.create_run(
        run_id="a", project_id=project.id, target_url="u", task="t",
        persona_ids=[], flow_name="signup",
    )
    await store.create_run(
        run_id="b", project_id=project.id, target_url="u", task="t",
        persona_ids=[], flow_name="checkout",
    )

    all_runs = await store.list_runs(project.id)
    assert {r.id for r in all_runs} == {"a", "b"}

    signup_only = await store.list_runs(project.id, flow_name="signup")
    assert [r.id for r in signup_only] == ["a"]


async def test_set_baseline_upsert_and_get(db_engine):
    store = Store()
    _user, project = await _make_project(store)

    await store.create_run(
        run_id="base-1", project_id=project.id, target_url="u", task="t",
        persona_ids=[], flow_name="signup",
    )
    await store.set_run_report("base-1", _report("base-1", 0.6))
    run1 = await store.get_run("base-1")

    b1 = await store.set_baseline(project.id, "signup", run1)
    assert b1.completion_rate == 0.6
    assert b1.run_id == "base-1"

    got = await store.get_baseline(project.id, "signup")
    assert got is not None and got.run_id == "base-1"

    # Upsert: a second call for the same (project, flow) updates the SAME row.
    await store.create_run(
        run_id="base-2", project_id=project.id, target_url="u", task="t",
        persona_ids=[], flow_name="signup",
    )
    await store.set_run_report("base-2", _report("base-2", 0.9))
    run2 = await store.get_run("base-2")

    b2 = await store.set_baseline(project.id, "signup", run2)
    assert b2.id == b1.id  # upsert, not a second insert
    assert b2.run_id == "base-2"
    assert b2.completion_rate == 0.9

    got2 = await store.get_baseline(project.id, "signup")
    assert got2.run_id == "base-2" and got2.completion_rate == 0.9


async def test_completion_trend_ordered_oldest_to_newest(db_engine):
    store = Store()
    _user, project = await _make_project(store)

    for rid, rate in [("t1", 0.2), ("t2", 0.5), ("t3", 0.8)]:
        await store.create_run(
            run_id=rid, project_id=project.id, target_url="u", task="t",
            persona_ids=[], flow_name="trendflow",
        )
        await store.set_run_report(rid, _report(rid, rate))
        await asyncio.sleep(0.02)  # guarantee strictly increasing created_at

    trend = await store.completion_trend(project.id, "trendflow")
    assert len(trend) == 3

    rates = [rate for (_ts, rate) in trend]
    assert rates == [0.2, 0.5, 0.8]  # oldest -> newest

    timestamps = [ts for (ts, _rate) in trend]
    assert timestamps == sorted(timestamps)

    # A different flow is not mixed in.
    assert await store.completion_trend(project.id, "other") == []
