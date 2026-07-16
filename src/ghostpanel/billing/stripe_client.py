"""Stripe wrapper — Agent P4-A. Signatures FROZEN (billing router imports).

Keeps all Stripe SDK calls behind these functions so the router stays testable
(tests monkeypatch this module) and so no live Stripe call happens without keys.
Test-mode until real STRIPE_SECRET_KEY is set — see docs/deploy.md.

Every entry point sets ``stripe.api_key`` locally from the passed ``secret_key``
so we never rely on a global mutable key set elsewhere in the process.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import stripe


@dataclass
class CheckoutSession:
    id: str
    url: str


@dataclass
class WebhookResult:
    """Normalized outcome of a verified webhook event the app should act on."""
    kind: str                      # "subscription_active" | "subscription_canceled" | "ignored"
    stripe_customer_id: str = ""
    stripe_subscription_id: str = ""
    # project_id resolved from checkout metadata (set when we created the session).
    project_id: str = ""


def is_configured(secret_key: str) -> bool:
    """True when a Stripe secret key is present (billing is live vs. test-stub)."""
    return bool(secret_key and secret_key.strip())


def create_checkout_session(
    *,
    secret_key: str,
    price_id: str,
    project_id: str,
    customer_email: str,
    success_url: str,
    cancel_url: str,
    quantity: int = 1,
    existing_customer_id: Optional[str] = None,
) -> CheckoutSession:
    """Create a Stripe Checkout session for the Team subscription. Put
    project_id in metadata so the webhook can map the subscription back to a
    project. Raise ValueError if not configured."""
    if not is_configured(secret_key):
        raise ValueError("Stripe is not configured (missing secret key).")

    stripe.api_key = secret_key

    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": quantity}],
        "metadata": {"project_id": project_id},
        # Mirror the metadata onto the subscription so subscription.updated /
        # .deleted webhooks (which carry the subscription, not the session)
        # can still resolve back to the project.
        "subscription_data": {"metadata": {"project_id": project_id}},
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    # Reuse an existing customer when we have one; otherwise let Stripe create
    # one prefilled with the user's email.
    if existing_customer_id:
        params["customer"] = existing_customer_id
    elif customer_email:
        params["customer_email"] = customer_email

    session = stripe.checkout.Session.create(**params)
    return CheckoutSession(id=session.id, url=session.url)


def create_billing_portal_session(
    *, secret_key: str, customer_id: str, return_url: str
) -> str:
    """Return a Stripe billing-portal URL for an existing customer."""
    if not is_configured(secret_key):
        raise ValueError("Stripe is not configured (missing secret key).")

    stripe.api_key = secret_key
    session = stripe.billing_portal.Session.create(
        customer=customer_id, return_url=return_url
    )
    return session.url


def parse_webhook(
    *, payload: bytes, signature: str, webhook_secret: str
) -> WebhookResult:
    """Verify the signature (stripe.Webhook.construct_event) and normalize the
    event into a WebhookResult. Unhandled event types -> kind='ignored'. Raise
    ValueError on signature failure."""
    try:
        event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
    except Exception as exc:  # SignatureVerificationError / bad payload
        raise ValueError(f"Invalid Stripe webhook signature: {exc}") from exc

    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {}) or {}
    metadata = obj.get("metadata") or {}
    project_id = metadata.get("project_id", "")

    if etype == "checkout.session.completed":
        return WebhookResult(
            kind="subscription_active",
            stripe_customer_id=obj.get("customer", "") or "",
            stripe_subscription_id=obj.get("subscription", "") or "",
            project_id=project_id,
        )

    if etype == "customer.subscription.updated":
        status = obj.get("status", "")
        if status in ("active", "trialing"):
            return WebhookResult(
                kind="subscription_active",
                stripe_customer_id=obj.get("customer", "") or "",
                stripe_subscription_id=obj.get("id", "") or "",
                project_id=project_id,
            )
        if status == "canceled":
            return WebhookResult(
                kind="subscription_canceled",
                stripe_customer_id=obj.get("customer", "") or "",
                stripe_subscription_id=obj.get("id", "") or "",
                project_id=project_id,
            )
        return WebhookResult(kind="ignored")

    if etype == "customer.subscription.deleted":
        return WebhookResult(
            kind="subscription_canceled",
            stripe_customer_id=obj.get("customer", "") or "",
            stripe_subscription_id=obj.get("id", "") or "",
            project_id=project_id,
        )

    return WebhookResult(kind="ignored")


__all__ = [
    "CheckoutSession", "WebhookResult", "is_configured",
    "create_checkout_session", "create_billing_portal_session", "parse_webhook",
]
