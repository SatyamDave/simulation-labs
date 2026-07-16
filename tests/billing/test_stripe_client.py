"""Stripe wrapper (billing/stripe_client.py, P4-A) — fully offline.

We never hit the network: the real ``stripe`` SDK is imported (so the impl's
``stripe.error.*`` references stay real), but the two SDK entry points the wrapper
uses — ``stripe.checkout.Session.create`` and ``stripe.Webhook.construct_event`` —
are monkeypatched. The module xfails (strict=False) while stripe_client is a stub.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import stripe

from ghostpanel.billing import stripe_client

from .conftest import is_stub

pytestmark = pytest.mark.xfail(
    is_stub(stripe_client.create_checkout_session),
    reason="billing/stripe_client.py still a stub (P4-A not landed)",
    strict=False,
)


class _Obj(dict):
    """A dict that also allows attribute access, mimicking a StripeObject so the
    impl can read either ``event['type']`` or ``event.type`` / ``event.data.object``."""

    __getattr__ = dict.get


# --------------------------------------------------------------------------- #
# is_configured
# --------------------------------------------------------------------------- #
def test_is_configured_true_when_key_present():
    assert stripe_client.is_configured("sk_test_abc") is True


def test_is_configured_false_when_blank():
    assert stripe_client.is_configured("") is False
    assert stripe_client.is_configured("   ") is False


# --------------------------------------------------------------------------- #
# create_checkout_session
# --------------------------------------------------------------------------- #
def test_create_checkout_session_builds_subscription_with_project_metadata(monkeypatch):
    calls: list[dict] = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.test/pay")

    monkeypatch.setattr(stripe.checkout.Session, "create", fake_create)

    result = stripe_client.create_checkout_session(
        secret_key="sk_test_abc",
        price_id="price_team_1",
        project_id="proj_abc",
        customer_email="founder@example.com",
        success_url="https://app.test/ok",
        cancel_url="https://app.test/no",
        quantity=3,
    )

    assert isinstance(result, stripe_client.CheckoutSession)
    assert result.id == "cs_test_123"
    assert result.url == "https://checkout.stripe.test/pay"

    assert len(calls) == 1
    kwargs = calls[0]
    assert kwargs.get("mode") == "subscription"
    # project_id must ride in metadata so the webhook can map back to the project.
    assert kwargs.get("metadata", {}).get("project_id") == "proj_abc"


def test_create_checkout_session_not_configured_raises(monkeypatch):
    # No SDK call should happen when there is no key.
    def boom(**kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("stripe.checkout.Session.create must not be called")

    monkeypatch.setattr(stripe.checkout.Session, "create", boom)
    with pytest.raises(ValueError):
        stripe_client.create_checkout_session(
            secret_key="",
            price_id="price_team_1",
            project_id="proj_abc",
            customer_email="founder@example.com",
            success_url="https://app.test/ok",
            cancel_url="https://app.test/no",
        )


# --------------------------------------------------------------------------- #
# parse_webhook
# --------------------------------------------------------------------------- #
def test_parse_webhook_checkout_completed_is_active(monkeypatch):
    event = _Obj(
        type="checkout.session.completed",
        data=_Obj(object=_Obj(
            customer="cus_1",
            subscription="sub_1",
            metadata=_Obj(project_id="proj_abc"),
        )),
    )
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    res = stripe_client.parse_webhook(
        payload=b"{}", signature="sig", webhook_secret="whsec_x"
    )
    assert res.kind == "subscription_active"
    assert res.stripe_customer_id == "cus_1"
    assert res.stripe_subscription_id == "sub_1"
    assert res.project_id == "proj_abc"


def test_parse_webhook_subscription_deleted_is_canceled(monkeypatch):
    event = _Obj(
        type="customer.subscription.deleted",
        data=_Obj(object=_Obj(
            id="sub_1",
            customer="cus_1",
            metadata=_Obj(project_id="proj_abc"),
        )),
    )
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    res = stripe_client.parse_webhook(
        payload=b"{}", signature="sig", webhook_secret="whsec_x"
    )
    assert res.kind == "subscription_canceled"


def test_parse_webhook_unhandled_event_is_ignored(monkeypatch):
    event = _Obj(type="invoice.paid", data=_Obj(object=_Obj()))
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    res = stripe_client.parse_webhook(
        payload=b"{}", signature="sig", webhook_secret="whsec_x"
    )
    assert res.kind == "ignored"


def test_parse_webhook_bad_signature_raises_value_error(monkeypatch):
    def boom(*a, **k):
        raise stripe.error.SignatureVerificationError("bad signature", "sig_header")

    monkeypatch.setattr(stripe.Webhook, "construct_event", boom)
    with pytest.raises(ValueError):
        stripe_client.parse_webhook(
            payload=b"{}", signature="bad", webhook_secret="whsec_x"
        )
