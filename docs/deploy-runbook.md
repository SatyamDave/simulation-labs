# Deploy runbook — Simulation Labs / Ghostpanel hosted backend

Operational companion to the staged pipeline in
[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml). It covers a
normal deploy, migrations, rollback, and a first-response incident checklist.

Read alongside:

- [`docs/deploy.md`](./deploy.md) — the deployment architecture, Fly.io setup,
  and the full operator production checklist (secrets, Postgres, storage).
- [`docs/migrations.md`](./migrations.md) — Alembic wiring, everyday commands,
  and the async→sync driver detail.

> **Targets are illustrative.** The pipeline uses Fly.io because the repo ships a
> `fly.toml`. If you deploy elsewhere (ECS, Cloud Run, k8s, Render), the shape —
> build → migrate → deploy → smoke → promote — is unchanged; only the deploy and
> smoke commands differ.

---

## The pipeline at a glance

```
push to main / workflow_dispatch
        │
   ┌────▼────┐   ┌─────────┐   ┌────────────────┐   ┌───────┐   ┌──────────────┐
   │  build  │──►│ migrate │──►│ deploy-staging │──►│ smoke │──►│  deploy-prod │
   └─────────┘   └─────────┘   └────────────────┘   └───────┘   └──────────────┘
   docker build   alembic       flyctl deploy        curl        (manual approval)
   → GHCR         upgrade head  → staging app        /healthz    prod migrate +
                  (STAGING DB)                       /readyz     flyctl deploy → prod
                  GATES deploy                       fail on     needs green smoke
                                                     non-200
```

- **`migrate` gates the deploy.** A failed `alembic upgrade head` stops the run
  before any code ships.
- **`smoke` gates promotion.** `curl -f` fails on any HTTP >= 400, so a broken
  staging deploy blocks `deploy-prod`.
- **`deploy-prod` waits for a human.** It targets the `production` GitHub
  Environment; with required reviewers configured, GitHub pauses for approval
  before the job runs.

---

## One-time operator setup

### Secrets — Settings ▸ Secrets and variables ▸ Actions ▸ Secrets

| Secret | What it is |
|--------|------------|
| `FLY_API_TOKEN` | Fly deploy token: `fly tokens create deploy`. Used for staging **and** prod. |
| `STAGING_DATABASE_URL` | Async SQLAlchemy URL of the **staging** Postgres: `postgresql+asyncpg://user:pw@host:5432/db`. |
| `PROD_DATABASE_URL` | Same, for the **production** Postgres. |
| `GITHUB_TOKEN` | Auto-provided by Actions (GHCR login for the build cache). No setup. |

### Variables — same page ▸ Variables (non-secret; defaults exist if unset)

| Variable | Default | Meaning |
|----------|---------|---------|
| `STAGING_FLY_APP` | `simulation-labs-staging` | Fly app name for staging. |
| `PROD_FLY_APP` | `simulation-labs` | Fly app name for production. |
| `STAGING_BASE_URL` | `https://simulation-labs-staging.fly.dev` | Staging URL smoke-tested. |
| `PROD_BASE_URL` | `https://simulation-labs.fly.dev` | Production URL smoke-tested post-deploy. |

### The `production` Environment — Settings ▸ Environments

Create an Environment named **`production`** and add **required reviewers**. This
is what makes `deploy-prod` pause for a manual approval. Without it, promotion is
automatic once smoke passes.

### Per-app Fly secrets (runtime config, NOT in CI)

Each Fly app (staging and prod) needs its own runtime secrets set once with
`fly secrets set` — `DATABASE_URL`, `SESSION_SECRET`, `HAI_API_KEY`, S3 creds,
etc. See the checklist in [`docs/deploy.md`](./deploy.md). The CI
`*_DATABASE_URL` secrets are only for running migrations from the runner; the
running app reads its own `DATABASE_URL` from `fly secrets`.

---

## Normal deploy

1. Merge to `main` (or trigger **Run workflow** on the Deploy action for
   `workflow_dispatch`).
2. Watch the run: `build` → `migrate` → `deploy-staging` → `smoke`.
3. When `smoke` is green the run pauses at `deploy-prod`. A reviewer approves in
   the run's UI (**Review deployments**).
4. `deploy-prod` migrates the prod DB, deploys, and re-smokes production.

Manual equivalent (from a laptop with `flyctl` and the venv, if CI is down):

```bash
# migrate first, then deploy — always in that order
DATABASE_URL="postgresql+asyncpg://…/staging" alembic upgrade head
flyctl deploy --app simulation-labs-staging --strategy rolling
# verify, then prod
DATABASE_URL="postgresql+asyncpg://…/prod" alembic upgrade head
flyctl deploy --app simulation-labs --strategy rolling
```

---

## Migrations

Full detail in [`docs/migrations.md`](./migrations.md). Deploy-relevant rules:

- **Migrate before the app boots.** The pipeline runs `alembic upgrade head`
  before `flyctl deploy`. Prod never calls `create_all` (dev-only).
- **Ship the migration with the model change** in the same commit.
- **Write forward-compatible migrations.** Because we do a *rolling* deploy, old
  and new code briefly run against the migrated schema at the same time. Prefer
  additive, backward-compatible changes (add nullable column, backfill, then in a
  later deploy make it non-null / drop the old one) so the in-flight old pods
  don't break. Avoid destructive changes in the same release as the code that
  stops using the column.
- **Check what's applied:** `DATABASE_URL=… alembic current` and `… alembic history`.

---

## Rollback

Roll back **code** and **schema** as separate decisions. Most incidents are
code — roll the release back first; only touch the schema if the migration
itself is the problem.

### Roll back the code (Fly release rollback)

```bash
# See recent releases (version, image, status, who/when)
flyctl releases --app simulation-labs

# Fastest: revert to the immediately previous release
flyctl releases rollback --app simulation-labs

# Or pin a specific known-good image (from `flyctl releases` / GHCR by SHA)
flyctl deploy --app simulation-labs \
  --image ghcr.io/<owner>/<repo>:<good-sha> \
  --strategy immediate
```

Every green build is pushed to GHCR tagged by commit SHA, so any prior good
commit is redeployable by tag.

### Roll back the schema (only if the migration is at fault)

```bash
DATABASE_URL="postgresql+asyncpg://…/prod" alembic downgrade -1
```

Downgrade **only** when the new migration is itself broken and no rolled-back
code depends on the new schema. If you followed the forward-compatible rule
above, a code rollback alone is usually enough and safer — a downgrade can drop
columns and lose data. When in doubt, roll back code, leave the schema, and fix
forward.

### Order of operations

- Bad **code**, good schema → roll back the release. Leave the DB.
- Bad **migration** → roll back the release, then `alembic downgrade -1` if the
  old code can't run against the new schema.
- Never downgrade a schema that the currently-running (rolled-back) code still
  needs.

---

## Incident checklist (first 15 minutes)

1. **Declare + timestamp.** Note start time and a one-line symptom. Open a
   channel/thread; assign one incident lead.
2. **Assess blast radius.** Is it staging or prod? Which probe is red?
   - `curl -i https://simulation-labs.fly.dev/healthz` (liveness — process up?)
   - `curl -i https://simulation-labs.fly.dev/readyz` (readiness — DB reachable?)
   - `flyctl status --app simulation-labs` and `flyctl logs --app simulation-labs`.
3. **Correlate with the last change.** Did an incident start right after a
   deploy? Check the Deploy action run and `flyctl releases`.
4. **Stop the bleeding — roll back first, diagnose later.** If a recent release
   is the likely cause, `flyctl releases rollback` now. Recovery beats a root
   cause in the moment.
5. **Check the worker, not just the API.** Runs execute in the `worker` process
   group (`fly.toml`). `flyctl logs --app … --group worker`. A healthy API with a
   dead worker means jobs queue but never run.
6. **Check dependencies.** Postgres reachable (`/readyz` covers this), S3/MinIO,
   and the Holo (HAI) rate limit — a saturated `HAI_RPM` looks like stuck jobs,
   not an outage.
7. **Verify recovery.** Re-run the smoke checks; confirm `/healthz` and `/readyz`
   are 200 and error rates are back to baseline.
8. **Write it up.** Timeline, root cause, and one concrete follow-up
   (test/alert/guardrail) so the same failure can't recur silently.

> Health probes are the source of truth throughout: `/healthz` = liveness (is the
> process up), `/readyz` = readiness (can it serve — it pings the database). The
> pipeline's smoke job asserts both return 200.
