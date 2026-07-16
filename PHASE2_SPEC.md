# Phase 2 spec — the hosted backend

> Frozen contract, built by parallel agents on disjoint paths (see how the repo
> itself was built). Do not change a frozen signature without updating this file and
> every owner. Do not edit files outside your ownership row. Do NOT run `git`.
> Use `source .venv/bin/activate`; deps are already installed (sqlmodel, aiosqlite,
> asyncpg, PyJWT, bcrypt, stripe, boto3). Async everywhere; `asyncio_mode=auto`.

## Goal
Turn the demo server into a real service: runs, baselines, and history persist;
runs execute as durable async jobs off an API; auth scopes everything to a project;
artifacts live behind a storage abstraction; the whole thing runs locally via
`docker compose up`. The Phase-1 CLI and engine are unchanged.

## What the orchestrator already froze (READ-ONLY for agents)
- `store/models.py` — the full SQLModel schema (User, Project, Membership, ApiKey,
  RunRow, BaselineRow, JobRow; enums Tier/Role/RunState/JobState). This is the contract.
- `store/db.py` — `get_engine/make_engine/set_engine/init_db/session_scope`.
- `storage/base.py` — the `ArtifactStorage` Protocol.
- `server/config.py` — `Settings` extended with `effective_database_url`, `session_secret`,
  `session_ttl_hours`, `storage_backend`, `s3_*`, `worker_concurrency`, `stripe_*`, `has_stripe`.
- The stub files below (signatures frozen; fill the bodies).

## Ownership map (no path appears twice)

| Owner | Owns (edit ONLY these) | Imports |
|-------|------------------------|---------|
| **P2-A Store** | `store/repo.py` | models, db |
| **P2-B Storage** | `storage/local.py`, `storage/s3.py`, `storage/factory.py` | storage/base, config |
| **P2-C Auth** | `auth/passwords.py`, `auth/tokens.py`, `auth/apikeys.py`, `auth/deps.py` | store, config |
| **P2-D Jobs** | `jobs/queue.py`, `jobs/worker.py` | store, storage, engine (SwarmManager), cli.driver patterns |
| **P2-E API** | `server/routers/auth.py`, `server/routers/projects.py`, `server/routers/runs.py`, `server/hosted.py` | store, auth, jobs, storage |
| **P2-F Deploy** | `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `fly.toml`, `docs/deploy.md` | — |
| **P2-G Tests** | `tests/store/**`, `tests/auth/**`, `tests/jobs/**`, `tests/server_v2/**` | all |

`store/*` = `src/ghostpanel/store/*`, etc. The orchestrator owns `pyproject.toml`,
`server/config.py`, `store/models.py`, `store/db.py`, `storage/base.py`, the stubs,
and the final `app.py` wiring (do NOT edit `server/app.py` or `server/api.py`).

## Frozen interfaces (fill the stub bodies exactly)
- **Store** (`store/repo.py`): all methods as declared. Open `session_scope()` per call;
  return detached ORM instances. `create_project` also inserts an OWNER Membership.
  `project_for_api_key` looks up by `prefix` then verifies the hash via
  `ghostpanel.auth.apikeys` and touches `last_used_at`. `set_run_report` stores
  `report.model_dump(mode="json")` + promoted `completion_rate` + FINISHED + `finished_at`.
- **Storage** (`storage/{local,s3,factory}.py`): implement `ArtifactStorage`.
  `LocalArtifactStorage(root: Path)` writes under `root/<run_id>/...` and `url_for` →
  `/artifacts/<run_id>/<rel>`. `S3ArtifactStorage` uses boto3 (lazy import) with
  `s3_endpoint_url`/`s3_region`; `url_for` → `s3_public_base_url` or the bucket URL.
  `build_storage(settings)` switches on `settings.storage_backend`.
- **Auth** (`auth/*`): bcrypt hashing; HS256 JWT (`sub`,`iat`,`exp`); API keys
  `sl_live_<8>_<secret>` (store prefix + hash of full key). `deps.py` reads
  `request.app.state.store` + `request.app.state.settings`; API key via
  `Authorization: Bearer sl_live_...` or `X-API-Key`; session via cookie `sl_session`
  or `Authorization: Bearer <jwt>`. Raise `fastapi.HTTPException` with 401/403.
- **Jobs** (`jobs/queue.py`, `jobs/worker.py`): durable queue as specced; `claim` atomic
  (Postgres `FOR UPDATE SKIP LOCKED`; SQLite guarded UPDATE + rowcount). Worker: shared
  browser + shared rate-limited `LiveHoloClient` (Settings.hai_rpm cap), claim→create RunRow
  (Store.create_run, state RUNNING)→drive `SwarmManager` to a RunReport→`Store.set_run_report`
  →`ArtifactStorage.put_dir(run_id, <engine artifact dir>/<run_id>)`→`mark_done`; on failure
  `Store.set_run_state(ERROR)` + `mark_failed`. Reuse the headless-swarm recipe from
  `ghostpanel/cli/driver.py` and `server/swarm.py` (do not import cli internals you don't need).

## API surface (P2-E) — mount under a router the orchestrator includes in app.py
`server/hosted.py` exposes `register_hosted(app, *, store, queue, storage, settings)` that
sets `app.state.store/queue/storage/settings` and `app.include_router(...)` for:
- `POST /v2/auth/signup {email,password}` → creates user + a first project, returns session + project.
- `POST /v2/auth/login` → sets `sl_session` cookie + returns token. `POST /v2/auth/logout`. `GET /v2/auth/me`.
- `GET /v2/projects` (user's), `POST /v2/projects {name}`, `GET /v2/projects/{id}`.
- `POST /v2/projects/{id}/keys {name}` → **plaintext once**, `GET .../keys`, `DELETE .../keys/{key_id}`.
- `POST /v2/runs` (API-key auth → project) `{url,task,persona_ids?,flow_name?}` → enqueue a job,
  create nothing else; return `{run_id?, job_id, status}`. (run_id may be assigned by the worker.)
- `GET /v2/runs?flow=&limit=&offset=` (project-scoped history), `GET /v2/runs/{run_id}`,
  `GET /v2/runs/{run_id}/report`, `GET /v2/runs/{run_id}/trend?flow=` (completion trend),
  `GET/POST /v2/projects/{id}/baselines` (get/set per flow).
Use the `auth/deps.py` dependencies for scoping. Return pydantic/plain JSON, never ORM objects raw.

## Definition of done (per agent)
Bodies implemented; `pytest tests/test_contracts.py` green; you touched only your row; no `git`.
P2-G writes offline tests (SQLite in-memory/temp file via `db.make_engine` + `db.set_engine`,
`init_db`) covering: Store CRUD + api-key roundtrip + trend; auth hashing/JWT/api-key verify + a
deps test via a tiny FastAPI app; queue enqueue/claim atomicity (two concurrent claims get
different jobs); storage local put/url; and an API smoke test with `httpx.AsyncClient`/TestClient
against `register_hosted` on a temp DB with the worker mocked. Use `pytest.mark.xfail(strict=False)`
guards for anything blocked on a sibling stub so the suite goes green as siblings land.
