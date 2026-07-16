# Phase 4 spec — monetization + multi-tenancy

> Frozen contract. Parallel agents, disjoint paths. Do NOT run `git`. Backend uses
> the venv (`source .venv/bin/activate`); stripe is installed. Build on Phase 2/3.

## Goal
Turn projects into billable tenants: Free / Team ($49/seat·mo) / Audit tiers with
entitlements (run quota, seats, private repos), Stripe checkout + portal + webhook
that syncs subscription → tier, seat/member management, and a dashboard billing +
members experience. Test-mode until real Stripe keys (docs/deploy.md).

## Frozen foundation (READ-ONLY — orchestrator owns)
- `billing/entitlements.py` — `TIER_LIMITS`, `Entitlements`, `QuotaExceeded`,
  `entitlements_for`, `check_can_enqueue`, `check_can_add_seat`, `check_can_add_flow`.
- `billing/stripe_client.py` — STUB you implement (P4-A): `is_configured`,
  `create_checkout_session`, `create_billing_portal_session`, `parse_webhook`
  (+ `CheckoutSession`, `WebhookResult`).
- `billing/usage.py` — STUB you implement (P4-A): `runs_this_period`, `member_count`,
  `list_members`, `add_member_by_email`, `remove_member`, `set_project_billing`
  (+ `MemberInfo`). Query the DB via `ghostpanel.store.db.session_scope` + models.
- Phase-2 models (Project.tier/stripe_customer_id/stripe_subscription_id/
  private_repos_enabled; Membership), `auth/deps.py` (`require_project_access`,
  `current_user`), Settings (`stripe_secret_key`, `stripe_webhook_secret`,
  `stripe_price_team`, `has_stripe`).

## Ownership map (no path appears twice)
| Owner | Owns |
|-------|------|
| **P4-A billing core** | `src/ghostpanel/billing/stripe_client.py`, `src/ghostpanel/billing/usage.py` |
| **P4-B billing+members API** | `src/ghostpanel/server/routers/billing.py`, `src/ghostpanel/server/routers/members.py` |
| **P4-C dashboard** | `web/src/dashboard/pages/Billing.tsx`, `web/src/dashboard/pages/Members.tsx`, `web/src/dashboard/api_billing.ts` |
| **P4-D tests** | `tests/billing/**` |

Orchestrator wires at integration: include the two routers in `server/hosted.py`;
add the enqueue quota check in `server/routers/runs.py`; add `/app/billing` +
`/app/members` routes in `web/src/main.tsx` and nav links in `DashboardLayout.tsx`;
add the billing client calls to `web/src/dashboard/api_billing.ts` consumers.

## P4-A — implement stripe_client.py + usage.py
- stripe_client: use the `stripe` SDK with the passed `secret_key` (set `stripe.api_key`
  locally per call; never global mutable surprises). `is_configured` = non-empty key.
  `create_checkout_session`: mode="subscription", line item `price_id`×quantity,
  `metadata={"project_id": project_id}`, `subscription_data.metadata` too, customer_email
  or existing_customer_id, success/cancel URLs; return CheckoutSession(id,url). `parse_webhook`:
  `stripe.Webhook.construct_event(payload, signature, webhook_secret)`; on
  `checkout.session.completed` / `customer.subscription.updated` (status active/trialing)
  → kind="subscription_active" with customer/subscription ids + project_id from metadata;
  on `customer.subscription.deleted` (or status canceled) → kind="subscription_canceled";
  else kind="ignored". Raise ValueError on bad signature.
- usage: implement all via session_scope. `runs_this_period` counts RunRow by project since
  the UTC month start. `add_member_by_email` looks up User by email (LookupError if none),
  guards duplicate (ValueError). `remove_member` refuses the owner. `set_project_billing`
  updates Project.tier (map str→Tier) + stripe ids + private_repos_enabled.

## P4-B — billing.py + members.py routers (APIRouter, /v2)
- billing.py:
  - `GET /v2/projects/{project_id}/billing` (require_project_access) → `{tier, entitlements,
    usage:{runs_this_period, seats}, stripe_configured}`.
  - `POST /v2/projects/{project_id}/billing/checkout` (require_project_access; owner) →
    create a Team checkout session (uses Settings.stripe_price_team, current_user email,
    success/cancel URLs from the request body or referer); return `{url}`. 400 if stripe not configured.
  - `POST /v2/projects/{project_id}/billing/portal` → `{url}` (needs stripe_customer_id).
  - `POST /v2/billing/webhook` (NO auth; raw body) → `parse_webhook` with Settings.stripe_webhook_secret;
    on active → `usage.set_project_billing(project_id, tier="team", ...ids, private_repos_enabled=True)`;
    on canceled → downgrade to "free", private_repos_enabled=False. Return `{received: true}`.
    Read the raw body via `await request.body()` and the `Stripe-Signature` header.
- members.py:
  - `GET /v2/projects/{project_id}/members` → list_members.
  - `POST /v2/projects/{project_id}/members {email, role?}` (owner) → check_can_add_seat(tier,
    member_count) then add_member_by_email; 402 on QuotaExceeded, 404 on unknown user, 409 on dup.
  - `DELETE /v2/projects/{project_id}/members/{user_id}` (owner) → remove_member; 400 if owner.
- Map `QuotaExceeded` → HTTP 402 with the message everywhere. Read `app.state.settings`.

## P4-C — dashboard Billing + Members pages + api_billing.ts
- `api_billing.ts`: typed client fns for the endpoints above, reusing the Bearer-token
  `req` pattern (import API_BASE + token handling from `./api2`, or replicate minimally).
  Export: `getBilling(projectId)`, `startCheckout(projectId, urls)`, `openPortal(projectId, url)`,
  `listMembers(projectId)`, `addMember(projectId,email,role?)`, `removeMember(projectId,userId)`.
- `Billing.tsx` (default export): show current plan + entitlements + usage (runs this period vs
  quota with a meter; seats). "Upgrade to Team" → startCheckout then `window.location = url`.
  "Manage billing" (portal) when subscribed. Handle 402 messages. If stripe not configured, show
  a "billing not enabled on this instance" note. Use activeProject from useAuth.
- `Members.tsx` (default export): list members (email, role), invite by email (calls addMember,
  shows 402 upgrade prompt / 404 "no such user"), remove (not owner). Match app Tailwind tokens.

## P4-D — tests/billing/**
- entitlements: quota/seat/flow guards (boundary cases, unlimited=-1).
- usage (temp sqlite via db.make_engine/set_engine/init_db + seeded rows): runs_this_period,
  member add/remove (owner-protected + dup + unknown-email), set_project_billing tier change.
- stripe_client: monkeypatch the `stripe` module — assert create_checkout_session builds the
  right params + metadata, parse_webhook maps event types → WebhookResult kinds, bad signature → ValueError.
- API (register_hosted + real Store on temp DB, stripe monkeypatched): GET billing shape;
  checkout 400 when unconfigured; webhook flips a project to team then back to free;
  members add/list/remove with 402 seat-limit on Free. Use xfail(strict=False) guards for
  anything still stubbed. Verify: `pytest tests/billing tests/test_contracts.py -q`.

## Definition of done
Your files implement the frozen signatures; `pytest tests/test_contracts.py` green; only your
row touched; no git. Backend agents: `pytest tests/billing -q` (or your own smoke). Frontend
agent: `npx tsc --noEmit` clean for your files.
