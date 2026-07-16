"""``/v2`` billing — plan summary, Stripe checkout/portal, and the webhook.

Owned by Agent P4-B. All Stripe/DB side effects go through the frozen
``ghostpanel.billing.stripe_client`` and ``ghostpanel.billing.usage`` modules
(imported as modules so tests can monkeypatch them). Settings are read off
``request.app.state.settings`` at request time — nothing is captured in a closure.

Auth:
  * summary            — ``require_project_access`` (member of the project).
  * checkout / portal  — the project **owner** (session user == ``project.owner_id``).
  * webhook            — NO auth; verified by the Stripe signature instead.
"""

from __future__ import annotations

import dataclasses

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ghostpanel.auth.deps import current_user, require_project_access
from ghostpanel.billing import stripe_client, usage
from ghostpanel.billing.entitlements import entitlements_for
from ghostpanel.store.models import Project

router = APIRouter(prefix="/v2", tags=["billing"])


# --- request models ---------------------------------------------------------
class CheckoutRequest(BaseModel):
    success_url: str = Field(..., min_length=1)
    cancel_url: str = Field(..., min_length=1)
    quantity: int = Field(1, ge=1)


class PortalRequest(BaseModel):
    return_url: str = Field(..., min_length=1)


# --- helpers ----------------------------------------------------------------
async def _require_owner(request: Request, project: Project) -> None:
    """Assert the calling session user owns ``project``; else 403."""
    user = await current_user(request)  # 401 if no session user
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="owner access required")


def _entitlements_dict(tier) -> dict:
    ent = entitlements_for(tier)
    d = dataclasses.asdict(ent)
    d["tier"] = ent.tier.value  # enum -> plain string
    return d


# --- routes -----------------------------------------------------------------
@router.get("/projects/{project_id}/billing")
async def get_billing(
    project_id: str,
    request: Request,
    project: Project = Depends(require_project_access),
) -> dict:
    settings = request.app.state.settings
    return {
        "tier": project.tier.value if hasattr(project.tier, "value") else str(project.tier),
        "entitlements": _entitlements_dict(project.tier),
        "usage": {
            "runs_this_period": await usage.runs_this_period(project.id),
            "seats": await usage.member_count(project.id),
        },
        "stripe_configured": stripe_client.is_configured(settings.stripe_secret_key),
    }


@router.post("/projects/{project_id}/billing/checkout")
async def start_checkout(
    project_id: str,
    body: CheckoutRequest,
    request: Request,
    project: Project = Depends(require_project_access),
) -> dict:
    await _require_owner(request, project)
    settings = request.app.state.settings
    if not stripe_client.is_configured(settings.stripe_secret_key):
        raise HTTPException(
            status_code=400, detail="Billing is not enabled on this instance."
        )
    user = await current_user(request)
    session = stripe_client.create_checkout_session(
        secret_key=settings.stripe_secret_key,
        price_id=settings.stripe_price_team,
        project_id=project.id,
        customer_email=user.email,
        success_url=body.success_url,
        cancel_url=body.cancel_url,
        quantity=body.quantity,
        existing_customer_id=project.stripe_customer_id or None,
    )
    return {"url": session.url}


@router.post("/projects/{project_id}/billing/portal")
async def open_portal(
    project_id: str,
    body: PortalRequest,
    request: Request,
    project: Project = Depends(require_project_access),
) -> dict:
    await _require_owner(request, project)
    settings = request.app.state.settings
    if not stripe_client.is_configured(settings.stripe_secret_key):
        raise HTTPException(
            status_code=400, detail="Billing is not enabled on this instance."
        )
    if not project.stripe_customer_id:
        raise HTTPException(
            status_code=400, detail="No Stripe customer for this project yet."
        )
    url = stripe_client.create_billing_portal_session(
        secret_key=settings.stripe_secret_key,
        customer_id=project.stripe_customer_id,
        return_url=body.return_url,
    )
    return {"url": url}


@router.post("/billing/webhook")
async def stripe_webhook(request: Request) -> dict:
    """Stripe webhook receiver (NO auth — verified by signature)."""
    settings = request.app.state.settings
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        result = stripe_client.parse_webhook(
            payload=payload,
            signature=signature,
            webhook_secret=settings.stripe_webhook_secret,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if result.kind == "subscription_active":
        await usage.set_project_billing(
            result.project_id,
            tier="team",
            stripe_customer_id=result.stripe_customer_id,
            stripe_subscription_id=result.stripe_subscription_id,
            private_repos_enabled=True,
        )
    elif result.kind == "subscription_canceled":
        await usage.set_project_billing(
            result.project_id,
            tier="free",
            stripe_customer_id=result.stripe_customer_id,
            stripe_subscription_id=result.stripe_subscription_id,
            private_repos_enabled=False,
        )

    return {"received": True}
