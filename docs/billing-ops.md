# Billing operations

How Simulation Labs keeps a project's plan (`Project.tier`, `private_repos_enabled`)
in sync with its Stripe subscription, and how to operate that safely.

There are two paths that mutate billing state:

1. **Webhooks (primary, event-driven).** `billing/stripe_client.parse_webhook`
   verifies the signature and normalizes Stripe events into a `WebhookResult`; the
   billing router applies them via `usage.set_project_billing`.
2. **Reconciliation (backstop, poll-based).** `billing/reconcile.py` re-derives the
   correct tier from Stripe's own view of the subscription and corrects any drift.
   Run it on a schedule and after any suspected webhook outage.

Both paths funnel through the same writer, `usage.set_project_billing`, so they can
never disagree about *how* to apply a change — only about *when*.

---

## Webhook idempotency (dedupe by Stripe event id)

Stripe guarantees **at-least-once** delivery: the same event can arrive more than
once (retries after a slow/failed 2xx, network hiccups, manual re-sends from the
Dashboard). A handler must therefore be safe to run repeatedly for the same event.

**Where we stand today.** Our application of an event is *naturally idempotent*:
`set_project_billing` sets tier + flags to an absolute target rather than applying a
delta, so replaying `customer.subscription.updated(status=active)` five times leaves
the project in exactly the same state as applying it once. There is no incrementing
counter or append that a duplicate could corrupt.

**Recommended follow-up: a processed-events table.** Natural idempotency covers
*state*, but not *side effects* (e.g. a future "send an upgrade receipt email" step
must fire once, not once per retry). Before we add any such side effect, introduce a
dedupe table keyed by the Stripe event id:

```sql
CREATE TABLE processed_stripe_events (
    event_id     TEXT PRIMARY KEY,   -- Stripe's evt_… id
    event_type   TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

In the handler, `INSERT ... ON CONFLICT (event_id) DO NOTHING`; if zero rows were
inserted the event was already processed → ack with 200 and skip. This makes the
whole handler idempotent regardless of side effects, and gives an audit trail. It is
tracked as a follow-up, not shipped, because the current handler has no
non-idempotent side effect.

## Replay protection

- **Signature + timestamp.** `stripe.Webhook.construct_event` (used by
  `parse_webhook`) verifies the `Stripe-Signature` HMAC against
  `STRIPE_WEBHOOK_SECRET` **and** enforces a default 5-minute tolerance on the
  signed timestamp, so a captured-and-replayed payload is rejected once it ages out.
  A bad or missing signature raises `ValueError` → the endpoint returns 400 and the
  event is not applied.
- Keep `STRIPE_WEBHOOK_SECRET` server-side only; rotate it via the Stripe Dashboard
  if it is ever exposed, and roll it with an overlap window so in-flight retries of
  already-signed events still verify.
- The processed-events table above also hardens against *application-level* replay:
  even a validly signed duplicate is a no-op after the first insert.

## Proration behavior

- Stripe prorates by default on mid-cycle plan changes (seat count changes, plan
  swaps). We rely on Stripe's proration rather than computing charges ourselves —
  the source of truth for money owed is always Stripe.
- Seat changes (Team is billed **$49 / seat · mo**) update the subscription quantity;
  Stripe issues a proration line for the remainder of the period and the amount is
  settled on the next invoice.
- Entitlement changes take effect immediately in-app the moment we observe the new
  subscription status (via webhook or reconcile); the *money* side is reconciled by
  Stripe's invoicing independently. We never gate access on invoice settlement
  timing — access follows subscription `status`.
- Downgrades to Free carry no proration credit by policy (documented on the pricing
  page); the customer keeps Team through the paid period, then reconcile moves them
  to Free once Stripe reports `canceled`.

## Failed-payment dunning

- When a renewal charge fails, Stripe moves the subscription to `past_due` and runs
  its **Smart Retries** dunning schedule (configurable retry cadence + customer
  emails via the Billing settings).
- **Reconcile deliberately does not downgrade `past_due` (or other transient states
  like `incomplete` / `paused`).** These are in `neither` set — see
  `_desired_state` returning `None` and `REASON_UNHANDLED_STATUS`. We keep the
  customer on Team during dunning so a transient card decline does not yank access.
- Terminal outcomes *are* acted on: if retries are exhausted Stripe transitions the
  subscription to `canceled` or `unpaid`, both in `INACTIVE_STATUSES`, and the next
  reconcile (or the `customer.subscription.deleted/updated` webhook) downgrades the
  project to Free with `private_repos` off.
- If you shorten or disable retries in Stripe, expect faster downgrades — the app
  will follow whatever terminal status Stripe reports.

---

## Reconciliation as a scheduled job

`reconcile_project(project_id, settings)` and `reconcile_all(settings)` live in
`billing/reconcile.py`.

**Contract of `reconcile_project`** — returns a dict:

```python
{
    "project_id": str,
    "before":  {"tier": str, "private_repos": bool} | None,
    "after":   {"tier": str, "private_repos": bool} | None,
    "changed": bool,
    "reason":  str,   # stripe_not_configured | project_not_found |
                      # no_subscription_id | in_sync | corrected | unhandled_status
}
```

Properties you can rely on:

- **Idempotent.** A second run against an already-correct project writes nothing and
  returns `changed=False, reason="in_sync"`.
- **Clean no-op** when Stripe is unconfigured (`reason="stripe_not_configured"`), the
  project is unknown (`project_not_found`), or it has no subscription id
  (`no_subscription_id`). In these cases Stripe is never called.
- **Absolute, not delta.** It sets the tier to the target derived from the live
  subscription status via `usage.set_project_billing`; it never wipes the Stripe
  customer/subscription ids (those args are omitted, and the writer preserves them).

Status → target mapping:

| Stripe status                                        | Target tier | `private_repos` |
|------------------------------------------------------|-------------|-----------------|
| `active`, `trialing`                                 | `team`      | on              |
| `canceled`, `unpaid`, `incomplete_expired`, `none`   | `free`      | off             |
| `past_due`, `incomplete`, `paused`, anything else    | *unchanged* (dunning/transient) |

**Running it.** Reconcile is a safe, read-mostly poll — schedule it and also run it
manually after any webhook-delivery incident:

```bash
# One project
python -c "import asyncio; from ghostpanel.server.config import get_settings; \
from ghostpanel.billing import reconcile; \
print(asyncio.run(reconcile.reconcile_project('<project_id>', get_settings())))"

# All subscribed projects (nightly cron / scheduled worker)
python -c "import asyncio; from ghostpanel.server.config import get_settings; \
from ghostpanel.billing import reconcile; \
[print(r) for r in asyncio.run(reconcile.reconcile_all(get_settings()))]"
```

Operational guidance:

- **Cadence:** nightly is plenty as a webhook backstop; run it on-demand after a
  Stripe webhook outage or a bulk Dashboard change.
- **Rate limits:** `reconcile_all` issues one `Subscription.retrieve` per subscribed
  project, sequentially. That is well within Stripe's limits for our volume; if the
  book of business grows large, page and add a small delay rather than parallelizing
  hard against Stripe.
- **Observability:** log every result where `changed=True` (a corrected drift is a
  signal a webhook was missed) and alert if the corrected-count spikes — that means
  the webhook path is degraded.
- **Safety:** `reconcile_all` returns `[]` immediately when Stripe is unconfigured,
  so it is safe to wire into every environment (dev/test included) without guards.
