# Data policy

How Simulation Labs handles the data it collects, stores, and deletes. This
document is the source of truth for retention windows, deletion-on-request, and
the sub-processors we rely on. It pairs with the operational tooling in
`ops/` (`backup.sh`, `restore.sh`, `retention.py`).

Simulation Labs runs swarms of behavioral synthetic personas against a
customer's live website to measure where real users would struggle or abandon a
flow (sign-up, checkout, cancel). The personas *act* on the target site, so the
data we produce is a recording of a real web application's behavior — which
makes some of it sensitive.

---

## 1. Data inventory

| Data | Where | Sensitivity | Notes |
|------|-------|-------------|-------|
| **Run artifacts — screenshots** | object storage (`ArtifactStorage`; local disk in dev, S3 in prod) under `<run_id>/…` | **High / potentially PII-bearing** | Frame-by-frame captures of the target site. If a persona reaches a page showing real data (a logged-in dashboard, an order confirmation, an email/name in the UI), that data is in the pixels. |
| **Run artifacts — video (`.webm`)** | object storage, per run | **High / potentially PII-bearing** | Full session recordings of the customer flow. Same exposure as screenshots, continuous. |
| **Run artifacts — exit-interview audio (`.wav`)** | object storage, per run | Medium | Synthetic (Gradium) voices narrating a persona's own action trace. No end-user voice; text is model-generated from the trace. |
| **Run artifacts — reports (`report.json`, `report.html`, heatmap PNG)** | object storage, per run | Medium | Survival curves, abandonment coordinates, captions. May embed thumbnails, so treat as screenshot-equivalent. |
| **Run metadata (`RunRow`)** | Postgres (`runs`) | Medium | `target_url`, `task`, `flow_name`, persona ids, `completion_rate`, timestamps, and the full `report_json`. |
| **Job records (`JobRow`)** | Postgres (`jobs`) | Low | Queue state, attempts, worker locks, run spec. |
| **Accounts (`User`)** | Postgres (`users`) | Medium | Email + bcrypt/sha password hash. No plaintext passwords. |
| **Projects / memberships** | Postgres (`projects`, `memberships`) | Low | Names, tiers, ownership, Stripe customer/subscription ids. |
| **API keys (`ApiKey`)** | Postgres (`api_keys`) | High (secret) | Only a `prefix` + a hash of the secret are stored; the full key is shown once at creation and never persisted. |
| **Billing** | Stripe (primary) + our `stripe_customer_id` / `stripe_subscription_id` | Medium | We do **not** store card numbers; Stripe is the system of record for payment instruments. |
| **Database backups** | `ops/backup.sh` output → `BACKUP_DIR` and/or `BACKUP_S3_BUCKET` | Inherits the DB's sensitivity | Logical `pg_dump` of the whole database. Treat backups as sensitive as production. |

**The most sensitive class is run artifacts** (screenshots + video), because the
personas drive a real site and whatever renders on screen is captured. Customers
are advised to run swarms against staging/test environments or accounts seeded
with synthetic data wherever possible.

---

## 2. Retention windows

| Data | Default retention | Enforced by |
|------|-------------------|-------------|
| Run artifacts (screenshots, video, audio, reports) | **90 days** from `created_at` | `ops/retention.py` (deletes artifacts + the `RunRow`) |
| Run metadata (`RunRow`) | **90 days** (deleted with its artifacts) | `ops/retention.py` |
| Job records (`JobRow`) | 90 days | routine cleanup / retention |
| Database backups | 30 days rolling | backup rotation (lifecycle rule on `BACKUP_S3_BUCKET`, or a cron prune of `BACKUP_DIR`) |
| Accounts, projects, memberships, API keys | Life of the account; deleted on account closure / request | account deletion flow |

`ops/retention.py` is the enforcement point for run data:

- **Dry-run is the default.** It prints a table of exactly which runs *would* be
  deleted and removes nothing until `--apply` is passed.
- It operates on the configured `DATABASE_URL` and **refuses** to touch the repo
  dev SQLite (`ghostpanel.db`), and any SQLite URL unless `--force-dev` is given.
- For each stale run it deletes the artifacts through the storage abstraction
  (local directory or S3 prefix) and then the database row inside a transaction.

Recommended schedule: run `python ops/retention.py --days 90 --apply` daily from
cron or a GitHub Actions scheduled workflow, next to the nightly `ops/backup.sh`.

Retention windows are defaults. Enterprise ("audit"-tier) customers may negotiate
a shorter window (e.g. delete artifacts within 24–72h of a run) or a longer one
for audit trails; set the window per environment via the `--days` flag.

---

## 3. Deletion on request (GDPR / CCPA)

We honor data-subject and customer deletion requests under GDPR (Art. 17, right
to erasure) and CCPA/CPRA (right to delete).

- **Run / project deletion.** A customer can request deletion of a specific run
  or an entire project. Runs are removed with `ops/retention.py` semantics
  (artifacts + row); a targeted deletion removes the named `run_id`s and all
  associated artifacts.
- **Account deletion.** On account closure we delete the `User`, their projects,
  memberships, API keys, and all runs + artifacts owned by those projects.
  Stripe customer records are canceled/deleted via the Stripe API.
- **Turnaround.** Deletion requests are actioned within **30 days** of a
  verified request; artifact deletion is typically same-day.
- **Backups.** Deleted data may persist in encrypted backups until those backups
  age out of the rolling **30-day** window, after which it is unrecoverable. We
  do not restore-then-re-delete individual records from backups; the backup
  window is the upper bound on residual retention.
- **Verification.** Requests are verified against the requesting account owner
  before any destructive action.

Contact: privacy@simulationlabs.example (replace with the production address).

---

## 4. Encryption

- **In transit.** All client/server and server/sub-processor traffic uses TLS
  (HTTPS to the API and the target sites; TLS to Postgres, S3, Stripe, and the
  Holo API).
- **At rest.**
  - *Object storage* (run artifacts, backups) is expected to have
    server-side encryption enabled — SSE-S3/SSE-KMS on AWS S3, or the
    equivalent on the S3-compatible endpoint. Enable a default-encryption bucket
    policy; do not store artifacts in an unencrypted bucket.
  - *Database* is expected to run with volume/at-rest encryption enabled
    (e.g. the managed Postgres provider's encrypted storage).
  - *Secrets* (`SESSION_SECRET`, `HAI_API_KEY`, `GRADIUM_API_KEY`,
    `STRIPE_SECRET_KEY`, AWS credentials) come only from the environment / a
    secrets manager — never committed. API keys are stored only as a hash.
- **Backups** produced by `ops/backup.sh` inherit the storage bucket's
  at-rest encryption; keep them in the same-or-stronger-encrypted bucket as
  production artifacts.

---

## 5. Sub-processors

| Sub-processor | Purpose | Data shared |
|---------------|---------|-------------|
| **H Company (Holo Models API)** | Persona perception/decision — the vision model that reads each screenshot and returns the next action. | Perturbed screenshots of the target site (sent as base64 image parts). This is how site pixels leave our infrastructure; scoped to the run. |
| **Gradium** | Text-to-speech / voice for exit-interview audio. | Model-generated interview text (derived from the action trace). No end-user audio. |
| **Anthropic (Claude)** | Turns a persona's action trace into a first-person exit-interview narrative. | The action trace + run context (text). |
| **Stripe** | Billing and payments; system of record for payment instruments. | Customer/subscription identifiers, billing email. We never see or store full card data. |
| **Object storage (AWS S3 or S3-compatible, e.g. MinIO)** | Durable storage of run artifacts and database backups. | All run artifacts + backups. |
| **NVIDIA NemoClaw / OpenShell** *(optional)* | Policy gateway that Holo inference can be routed through, when configured. | Same screenshots as the Holo path, when the gateway is enabled. |

Customers running swarms against sites containing real end-user data should
account for H Company (screenshots) and their object-storage provider as
recipients of that data, and prefer staging environments or synthetic accounts.

We maintain data-processing terms with each sub-processor and update this list
before adding a new one.
