# Simulation Labs — hosted API reference (`/v2`)

Base URL: your deployment (dev: `http://localhost:8000`). All bodies are JSON.

## Auth modes
- **Session JWT** (dashboard): `signup`/`login` return a `token`; send it as
  `Authorization: Bearer <jwt>` (also set as the `sl_session` httponly cookie).
- **Project API key** (CLI / CI): `Authorization: Bearer sl_live_...` or `X-API-Key: sl_live_...`.
  Scopes every call to that key's project. Create keys in the dashboard (Settings) or via the API.

Errors use `{"detail": "..."}` with status: `401` (no/invalid auth), `402` (over tier quota —
upgrade), `403` (not permitted), `404` (unknown / hidden cross-tenant), `409` (conflict),
`425` (run report not ready yet).

## Auth
| Method | Path | Auth | Body → Response |
|--------|------|------|-----------------|
| POST | `/v2/auth/signup` | none | `{email, password}` → `{user, project, token}` (201); creates a Default project |
| POST | `/v2/auth/login` | none | `{email, password}` → `{user, token}` (+ cookie) |
| POST | `/v2/auth/logout` | session | → clears cookie |
| GET | `/v2/auth/me` | session | → `{user, projects[]}` |

## Projects & API keys
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/v2/projects` | session | your projects |
| POST | `/v2/projects` | session | `{name}` → project |
| GET | `/v2/projects/{id}` | member | project |
| GET | `/v2/projects/{id}/keys` | member | key rows (no secret) |
| POST | `/v2/projects/{id}/keys` | member | `{name}` → `{key, plaintext}` — **plaintext shown once** |
| DELETE | `/v2/projects/{id}/keys/{key_id}` | member | revoke |

## Runs
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/v2/runs` | API key | `{url, task, persona_ids?, flow_name?}` → `{job_id, run_id?, status}` (202). Enforces SSRF guard (400 on internal URL) + monthly quota (402). |
| GET | `/v2/runs?project_id=&flow=&limit=&offset=` | API key or session+project | run summaries (newest first) |
| GET | `/v2/runs/{run_id}` | scoped | run summary (404 if not in your project) |
| GET | `/v2/runs/{run_id}/report` | scoped | full `RunReport` JSON (425 if not finished) |
| GET | `/v2/runs/{run_id}/trend?flow=` | scoped | `[{created_at, completion_rate}]` |
| GET | `/v2/projects/{id}/baselines?flow=` | member | baselines |
| POST | `/v2/projects/{id}/baselines` | member | `{flow_name, run_id}` → baseline (from a finished run) |

## Billing (Phase 4)
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/v2/projects/{id}/billing` | member | `{tier, entitlements, usage:{runs_this_period, seats}, stripe_configured}` |
| POST | `/v2/projects/{id}/billing/checkout` | owner | `{success_url, cancel_url}` → `{url}` (Stripe Checkout; 400 if Stripe not configured) |
| POST | `/v2/projects/{id}/billing/portal` | owner | `{return_url}` → `{url}` (needs a Stripe customer) |
| POST | `/v2/billing/webhook` | Stripe signature | raw body + `Stripe-Signature`; syncs subscription → tier |

## Members / seats
| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/v2/projects/{id}/members` | member | `[{user_id, email, role}]` |
| POST | `/v2/projects/{id}/members` | owner | `{email, role?}` → member (402 over seat limit, 404 unknown user, 409 dup) |
| DELETE | `/v2/projects/{id}/members/{user_id}` | owner | remove (400 for the owner) |

## Ops
| GET | `/healthz` | none | liveness |
| GET | `/readyz` | none | `{status, db}` readiness (checks the DB) |

Every response carries an `X-Request-ID` header (accepts an inbound one) for log correlation.
