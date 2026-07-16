# Deploying the Simulation Labs hosted backend

This is the Phase-2 hosted service: a FastAPI API, a durable job **worker**, a
Postgres database, and S3-compatible artifact storage. It packages as a single
Docker image (`Dockerfile`) that runs in one of two roles — API or worker.

The image is based on `mcr.microsoft.com/playwright/python:v1.55.0-jammy`, which
ships Chromium and all the system libraries the swarm's headless browser needs.

---

## 1. Run it locally with Docker Compose

Everything comes up with one command. You only need a Holo (HAI) API key to run
real swarms; without it the API and worker still boot (jobs that call Holo will
fail).

```bash
# From the repo root. Provide your key via the host env (or a .env file):
export HAI_API_KEY=hk-xxxxxxxxxxxxxxxxxxxx
# optional: export GRADIUM_API_KEY=gd-...  ANTHROPIC_API_KEY=sk-ant-...

docker compose up --build
```

This starts:

| Service        | What it is                          | URL / port |
|----------------|-------------------------------------|------------|
| `db`           | Postgres 16                         | `localhost:5432` |
| `minio`        | S3-compatible object store          | API `localhost:9000`, console `localhost:9001` |
| `createbucket` | one-shot: creates the bucket, exits | —          |
| `api`          | the FastAPI API (uvicorn)           | `http://localhost:8000` |
| `worker`       | durable job runner (`ghostpanel-worker`) | —     |

Health check: `curl http://localhost:8000/healthz`.

### MinIO console + the bucket

The `createbucket` service runs automatically and creates the `ghostpanel`
bucket (name from `S3_BUCKET`, default `ghostpanel`) with public-download
access, so artifact URLs resolve in the browser.

Open the console at **http://localhost:9001** and log in with
`minioadmin` / `minioadmin` to browse uploaded video receipts, reports, and
audio. If you ever need to recreate the bucket manually:

```bash
docker compose run --rm createbucket
```

### First signup → project → API key → run

The API scopes everything to a **project**, and runs are authenticated with a
**project API key**. Bootstrap with the `/v2` endpoints:

```bash
# 1. Sign up. Creates a user + a first project, returns a session cookie/token.
curl -s -c cookies.txt -X POST http://localhost:8000/v2/auth/signup \
  -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"correct-horse-battery-staple"}'

# 2. Find your project id.
curl -s -b cookies.txt http://localhost:8000/v2/projects

# 3. Mint an API key (the plaintext key is returned exactly ONCE — save it).
curl -s -b cookies.txt -X POST \
  http://localhost:8000/v2/projects/<PROJECT_ID>/keys \
  -H 'content-type: application/json' -d '{"name":"ci"}'
# -> {"key":"sl_live_xxxxxxxx_...."}   <-- copy this now

# 4. Enqueue a run with the API key (the worker picks it up).
curl -s -X POST http://localhost:8000/v2/runs \
  -H 'authorization: Bearer sl_live_xxxxxxxx_....' \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com","task":"Sign up for an account"}'
# -> {"job_id":"...","status":"queued", ...}
```

### Point the CLI / GitHub Action at it

The `sl_live_...` key is what the CLI and the CI gate authenticate with. Set it
as `HAI_API_KEY`'s hosted counterpart in your environment / CI secrets and point
the client at your API base URL (`http://localhost:8000` locally, your domain in
prod). In a GitHub workflow using the composite Action (`action.yml`), pass the
key via `secrets` exactly as the [CI docs](./ci.md) describe.

---

## 2. Deploy to Fly.io

`fly.toml` defines two process groups off one image: `app` (the public API with
a `/healthz` check) and `worker` (the queue drainer, no inbound traffic).

```bash
fly launch --no-deploy         # first time only; keep the provided fly.toml
fly secrets set \
  DATABASE_URL="postgresql+asyncpg://USER:PASS@HOST:5432/DB" \
  SESSION_SECRET="$(openssl rand -hex 32)" \
  HAI_API_KEY="hk-..." \
  S3_BUCKET="..." S3_REGION="..." S3_ENDPOINT_URL="..." \
  AWS_ACCESS_KEY_ID="..." AWS_SECRET_ACCESS_KEY="..."
fly deploy
fly scale count app=1 worker=1
```

`DATABASE_URL` and all secrets are injected via `fly secrets` — they are never
committed to `fly.toml`.

---

## 3. Production checklist — these are OPERATOR steps, not done for you

The compose stack is a convenient dev environment. Standing up a real,
durable production deployment requires deliberate human decisions. Nothing below
is automated — you must do each one.

- [ ] **Provision a managed Postgres.** Do not run the compose `db` in prod.
      Use a managed instance (Fly Postgres, RDS, Neon, Supabase, …) and set
      `DATABASE_URL=postgresql+asyncpg://USER:PASS@HOST:5432/DB`.

- [ ] **Adopt Alembic migrations BEFORE relying on Postgres.** The app's
      `init_db` uses SQLAlchemy `create_all`, which is **dev-only**: it creates
      missing tables but never alters or migrates an existing schema. For any
      database you intend to keep, introduce Alembic (or an equivalent) and run
      migrations as a deploy step. Treat `create_all` as scaffolding, not a
      migration tool.

- [ ] **Set a strong `SESSION_SECRET`.** The default
      (`dev-insecure-secret-change-me`) must never reach production — session
      JWTs are signed with it. Generate one with `openssl rand -hex 32` and set
      it as a secret. Rotating it invalidates all existing sessions.

- [ ] **Set `HAI_API_KEY`** (and `HAI_RPM` to your real Holo tier). The worker
      shares one rate-limited client across the swarm; do not exceed your tier.

- [ ] **Choose artifact storage.** For prod use `STORAGE_BACKEND=s3` with a real
      bucket: set `S3_BUCKET`, `S3_REGION`, optionally `S3_ENDPOINT_URL` (for
      non-AWS S3) and `S3_PUBLIC_BASE_URL` (CDN/public base for artifact links).
      Credentials come from the standard boto3 chain — set
      `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (or an instance role). These
      two are boto3's own env vars, not `Settings` fields. `STORAGE_BACKEND=local`
      only works if the API and worker share a persistent filesystem.

- [ ] **Set `WORKER_CONCURRENCY`** for the worker to match your Holo RPM budget
      and browser memory headroom (keep it small; Chromium is heavy).

- [ ] **Billing (Phase 4).** When you turn on billing, set `STRIPE_SECRET_KEY`,
      `STRIPE_WEBHOOK_SECRET`, and `STRIPE_PRICE_TEAM`. They are inert until set,
      so the service runs fine without them until then.

- [ ] **Optional integrations.** `GRADIUM_API_KEY` enables voice exit-interviews;
      `ANTHROPIC_API_KEY` powers the exit-interview narration. Both are optional.

- [ ] **Configure a domain + TLS.** On Fly, `force_https` is on and Fly
      terminates TLS; add your certificate with `fly certs add your-domain`.
      Behind your own proxy, terminate TLS there and forward to port 8000.

- [ ] **Run at least one `worker` process** alongside the API — the API only
      enqueues jobs; nothing executes runs without a worker.

### Environment variables (all resolved in `server/config.py`)

`DATABASE_URL`, `SESSION_SECRET`, `SESSION_TTL_HOURS`, `STORAGE_BACKEND`,
`S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_REGION`, `S3_PUBLIC_BASE_URL`,
`WORKER_CONCURRENCY`, `HAI_API_KEY`, `HAI_BASE_URL`, `HAI_MODEL`, `HAI_RPM`,
`GRADIUM_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `GHOSTPANEL_HOST`,
`GHOSTPANEL_PORT`, `GHOSTPANEL_ARTIFACT_DIR`, `STRIPE_SECRET_KEY`,
`STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_TEAM`, `NEMOCLAW_GATEWAY_URL`.

`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` are read by
boto3 directly (the S3 backend builds its client from the default credential
chain), not by `Settings`.
