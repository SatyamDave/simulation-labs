"""Billing + members HTTP surface (P4-B routers) over ``register_hosted``.

Real Store + real JobQueue on a temp SQLite DB — exactly the harness the Phase-2
API tests use — with ``ghostpanel.billing.stripe_client`` monkeypatched so nothing
touches Stripe or the network. The whole module xfails (strict=False) until the
billing/members routers exist, the billing core is implemented, AND ``register_hosted``
wires the routers; it flips to real coverage as those land.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from .conftest import is_stub

try:
    from ghostpanel.server.hosted import register_hosted
    _HOSTED_ERR: Exception | None = None
except Exception as exc:  # noqa: BLE001
    register_hosted = None  # type: ignore[assignment]
    _HOSTED_ERR = exc


def _api_blocked() -> tuple[bool, str]:
    if register_hosted is None:
        return True, f"server.hosted.register_hosted unavailable ({_HOSTED_ERR!r})"
    try:
        from ghostpanel.server.routers import billing as _b  # noqa: F401
        from ghostpanel.server.routers import members as _m  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return True, f"billing/members routers not present yet ({exc!r})"
    from ghostpanel.billing import stripe_client, usage

    if is_stub(usage.set_project_billing) or is_stub(stripe_client.create_checkout_session):
        return True, "billing core (usage/stripe_client) still stubbed (P4-A)"
    try:
        src = inspect.getsource(register_hosted)
    except (OSError, TypeError):
        src = ""
    if "billing" not in src and "members" not in src:
        return True, "register_hosted does not wire the billing/members routers yet"
    return False, ""


_BLOCKED, _REASON = _api_blocked()
pytestmark = pytest.mark.xfail(_BLOCKED, reason=_REASON, strict=False)


# --------------------------------------------------------------------------- #
# harness
# --------------------------------------------------------------------------- #
def _build_client(tmp_path, *, stripe_secret_key: str = "", stripe_webhook_secret: str = "whsec_test") -> TestClient:
    from ghostpanel.jobs.queue import JobQueue
    from ghostpanel.server.config import Settings
    from ghostpanel.storage.local import LocalArtifactStorage
    from ghostpanel.store import db
    from ghostpanel.store.repo import Store

    url = f"sqlite+aiosqlite:///{tmp_path / 'api.db'}"
    settings = Settings(
        database_url=url,
        session_secret="billing-test-secret",
        artifact_dir=tmp_path / "artifacts",
        storage_backend="local",
        stripe_secret_key=stripe_secret_key,
        stripe_webhook_secret=stripe_webhook_secret,
        stripe_price_team="price_team_1",
    )

    app = FastAPI()

    @app.on_event("startup")
    async def _startup():
        engine = db.make_engine(url)
        db.set_engine(engine)
        await db.init_db(engine)

    @app.on_event("shutdown")
    async def _shutdown():
        engine = db.get_engine()
        await engine.dispose()
        db.set_engine(None)

    register_hosted(
        app,
        store=Store(),
        queue=JobQueue(),
        storage=LocalArtifactStorage(settings.artifact_dir),
        settings=settings,
    )
    return TestClient(app)


def _signup(c, email="founder@example.com", password="hunter2hunter2") -> str:
    resp = c.post("/v2/auth/signup", json={"email": email, "password": password})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["project"]["id"]


def _login(c, email="founder@example.com", password="hunter2hunter2") -> None:
    resp = c.post("/v2/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text


def _fake_stripe(monkeypatch, *, configured=True, checkout_url="https://checkout.stripe.test/pay"):
    from ghostpanel.billing import stripe_client

    monkeypatch.setattr(stripe_client, "is_configured", lambda key: configured, raising=False)
    monkeypatch.setattr(
        stripe_client,
        "create_checkout_session",
        lambda **kwargs: stripe_client.CheckoutSession(id="cs_test_1", url=checkout_url),
        raising=False,
    )
    return stripe_client


def _webhook(c, monkeypatch, project_id: str, kind: str):
    """POST a webhook whose parse_webhook is stubbed to the given normalized kind."""
    from ghostpanel.billing import stripe_client

    result = stripe_client.WebhookResult(
        kind=kind,
        stripe_customer_id="cus_1",
        stripe_subscription_id="sub_1",
        project_id=project_id,
    )
    monkeypatch.setattr(stripe_client, "parse_webhook", lambda **kwargs: result, raising=False)
    return c.post(
        "/v2/billing/webhook",
        content=b'{"fake":"event"}',
        headers={"Stripe-Signature": "t=1,v1=deadbeef"},
    )


# --------------------------------------------------------------------------- #
# GET billing summary
# --------------------------------------------------------------------------- #
def test_billing_summary_shape_defaults_to_free(tmp_path, monkeypatch):
    _fake_stripe(monkeypatch, configured=False)
    client = _build_client(tmp_path, stripe_secret_key="")
    with client as c:
        pid = _signup(c)
        resp = c.get(f"/v2/projects/{pid}/billing")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["tier"] == "free"
        assert "entitlements" in body
        assert body["usage"]["runs_this_period"] == 0
        assert body["usage"]["seats"] == 1
        assert body["stripe_configured"] is False


# --------------------------------------------------------------------------- #
# checkout
# --------------------------------------------------------------------------- #
def test_checkout_400_when_stripe_unconfigured(tmp_path, monkeypatch):
    _fake_stripe(monkeypatch, configured=False)
    client = _build_client(tmp_path, stripe_secret_key="")
    with client as c:
        pid = _signup(c)
        resp = c.post(
            f"/v2/projects/{pid}/billing/checkout",
            json={"success_url": "https://app.test/ok", "cancel_url": "https://app.test/no"},
        )
        assert resp.status_code == 400, resp.text


def test_checkout_returns_url_when_configured(tmp_path, monkeypatch):
    _fake_stripe(monkeypatch, configured=True, checkout_url="https://checkout.stripe.test/go")
    client = _build_client(tmp_path, stripe_secret_key="sk_test_abc")
    with client as c:
        pid = _signup(c)
        resp = c.post(
            f"/v2/projects/{pid}/billing/checkout",
            json={"success_url": "https://app.test/ok", "cancel_url": "https://app.test/no"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["url"] == "https://checkout.stripe.test/go"


# --------------------------------------------------------------------------- #
# webhook flips tier both ways
# --------------------------------------------------------------------------- #
def test_webhook_activates_then_cancels_subscription(tmp_path, monkeypatch):
    _fake_stripe(monkeypatch, configured=True)
    client = _build_client(tmp_path, stripe_secret_key="sk_test_abc")
    with client as c:
        pid = _signup(c)

        active = _webhook(c, monkeypatch, pid, "subscription_active")
        assert active.status_code == 200, active.text
        assert c.get(f"/v2/projects/{pid}/billing").json()["tier"] == "team"

        canceled = _webhook(c, monkeypatch, pid, "subscription_canceled")
        assert canceled.status_code == 200, canceled.text
        assert c.get(f"/v2/projects/{pid}/billing").json()["tier"] == "free"


# --------------------------------------------------------------------------- #
# members: seat gating + list + remove
# --------------------------------------------------------------------------- #
def test_members_seat_limit_then_upgrade_then_remove(tmp_path, monkeypatch):
    _fake_stripe(monkeypatch, configured=True)
    client = _build_client(tmp_path, stripe_secret_key="sk_test_abc")
    with client as c:
        pid = _signup(c, email="owner@example.com")
        # Create a real user to invite, then return to the owner session.
        _signup(c, email="teammate@example.com")
        _login(c, email="owner@example.com")

        # Free tier: owner already holds the single seat -> 402.
        blocked = c.post(f"/v2/projects/{pid}/members", json={"email": "teammate@example.com"})
        assert blocked.status_code == 402, blocked.text

        # Upgrade to Team via webhook, then the invite succeeds.
        assert _webhook(c, monkeypatch, pid, "subscription_active").status_code == 200
        added = c.post(f"/v2/projects/{pid}/members", json={"email": "teammate@example.com"})
        assert added.status_code in (200, 201), added.text

        # List reflects both members.
        listing = c.get(f"/v2/projects/{pid}/members")
        assert listing.status_code == 200, listing.text
        members = listing.json()
        members = members if isinstance(members, list) else members.get("members")
        by_email = {m["email"]: m for m in members}
        assert set(by_email) == {"owner@example.com", "teammate@example.com"}

        teammate_id = by_email["teammate@example.com"]["user_id"]
        owner_id = by_email["owner@example.com"]["user_id"]

        # Remove the teammate -> ok; removing the owner -> 400.
        removed = c.request("DELETE", f"/v2/projects/{pid}/members/{teammate_id}")
        assert removed.status_code in (200, 204), removed.text
        refuse_owner = c.request("DELETE", f"/v2/projects/{pid}/members/{owner_id}")
        assert refuse_owner.status_code == 400, refuse_owner.text


def test_members_add_unknown_user_is_404(tmp_path, monkeypatch):
    _fake_stripe(monkeypatch, configured=True)
    client = _build_client(tmp_path, stripe_secret_key="sk_test_abc")
    with client as c:
        pid = _signup(c, email="owner@example.com")
        assert _webhook(c, monkeypatch, pid, "subscription_active").status_code == 200
        resp = c.post(f"/v2/projects/{pid}/members", json={"email": "ghost@example.com"})
        assert resp.status_code == 404, resp.text
