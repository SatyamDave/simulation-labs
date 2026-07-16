#!/usr/bin/env python3
"""ops/retention.py — delete run data past its retention window.

Finds ``RunRow`` records older than ``--days`` (by ``created_at``) and, for each,
deletes its artifacts (screenshots / video / audio / report) through the storage
abstraction and then the database row via ``session_scope``. Run artifacts are
recordings of real customer flows and are the most sensitive data we hold, so
this is the enforcement point for the retention windows documented in
``docs/data-policy.md``.

SAFETY
------
* Dry-run is the DEFAULT. Nothing is deleted unless you pass ``--apply``.
* It operates on the configured ``DATABASE_URL`` (via ``get_settings()``), never
  on a hardcoded path.
* It refuses to run against the repo's dev SQLite (``ghostpanel.db``) always, and
  against any SQLite URL unless you pass ``--force-dev`` (intended for tests).

Usage
-----
    python ops/retention.py                      # dry-run, 90-day window
    python ops/retention.py --days 30            # dry-run, 30-day window
    python ops/retention.py --days 30 --apply    # actually delete
    DATABASE_URL=sqlite+aiosqlite:///:memory: \\
        python ops/retention.py --dry-run --force-dev   # tests / local

Schedule the ``--apply`` variant from cron / a GitHub Actions scheduled workflow
alongside ops/backup.sh (see docs/data-policy.md).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import shutil
import sys
from pathlib import Path
from typing import Optional

# Make the editable package importable even if run before `pip install -e`.
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sqlmodel import select  # noqa: E402

from ghostpanel.server.config import get_settings  # noqa: E402
from ghostpanel.store.db import make_engine, session_scope  # noqa: E402
from ghostpanel.store.models import RunRow  # noqa: E402
from ghostpanel.storage.factory import build_storage  # noqa: E402
from ghostpanel.storage.local import LocalArtifactStorage  # noqa: E402
from ghostpanel.storage.s3 import S3ArtifactStorage  # noqa: E402


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _as_aware(value: _dt.datetime) -> _dt.datetime:
    """Normalize a possibly-naive datetime (SQLite loses tzinfo) to UTC-aware."""
    if value.tzinfo is None:
        return value.replace(tzinfo=_dt.timezone.utc)
    return value


def _is_sqlite(url: str) -> bool:
    return url.strip().lower().startswith("sqlite")


def _is_repo_dev_db(url: str) -> bool:
    """True if the URL points at the repo's committed dev SQLite (ghostpanel.db)."""
    return "ghostpanel.db" in url


# --------------------------------------------------------------------------- #
# Artifact deletion. The frozen ArtifactStorage Protocol has no delete method,
# so we branch on the concrete backend here rather than mutate the abstraction.
# --------------------------------------------------------------------------- #
def _local_delete(storage: LocalArtifactStorage, run_id: str) -> int:
    run_dir = storage.root / run_id
    if not run_dir.is_dir():
        return 0
    count = sum(1 for p in run_dir.rglob("*") if p.is_file())
    shutil.rmtree(run_dir, ignore_errors=True)
    return count


def _s3_delete(storage: S3ArtifactStorage, run_id: str) -> int:
    """List and delete every object under the ``<run_id>/`` prefix."""
    client = storage._get_client()  # lazy boto3 client
    prefix = f"{run_id}/"
    deleted = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=storage.bucket, Prefix=prefix):
        keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if not keys:
            continue
        client.delete_objects(Bucket=storage.bucket, Delete={"Objects": keys})
        deleted += len(keys)
    return deleted


async def _delete_artifacts(storage, run_id: str) -> int:
    """Delete all artifacts for ``run_id``; return the number of files removed."""
    if isinstance(storage, LocalArtifactStorage):
        return await asyncio.to_thread(_local_delete, storage, run_id)
    if isinstance(storage, S3ArtifactStorage):
        return await asyncio.to_thread(_s3_delete, storage, run_id)
    # Unknown backend: don't guess how to delete; report zero and leave it.
    print(f"  ! unknown storage backend {type(storage).__name__!r}; "
          f"skipped artifact deletion for {run_id}")
    return 0


def _print_table(rows: list[RunRow]) -> None:
    header = f"{'run_id':<34}  {'project_id':<34}  {'state':<9}  {'created_at (UTC)':<20}  compl"
    print(header)
    print("-" * len(header))
    for r in rows:
        created = _as_aware(r.created_at).strftime("%Y-%m-%d %H:%M:%S")
        compl = "-" if r.completion_rate is None else f"{r.completion_rate:.2f}"
        print(f"{r.id:<34}  {r.project_id:<34}  {r.state.value:<9}  {created:<20}  {compl}")


async def run_retention(*, days: int, dry_run: bool, force_dev: bool) -> int:
    """Core logic. Returns the number of runs deleted (or that WOULD be deleted)."""
    settings = get_settings()
    db_url = settings.effective_database_url

    # --- guards ---------------------------------------------------------- #
    if _is_repo_dev_db(db_url):
        print("REFUSING: DATABASE_URL points at the repo dev SQLite "
              "(ghostpanel.db). Retention never runs against the dev database.",
              file=sys.stderr)
        return -1
    if _is_sqlite(db_url) and not force_dev:
        print(f"REFUSING: DATABASE_URL looks like SQLite ({db_url!r}). "
              "Pass --force-dev to allow (intended for tests only).",
              file=sys.stderr)
        return -1

    cutoff = _now() - _dt.timedelta(days=days)
    mode = "DRY-RUN (no deletions)" if dry_run else "APPLY (deleting)"
    print(f"Retention {mode}")
    print(f"  database: {db_url}")
    print(f"  storage:  {settings.storage_backend}")
    print(f"  cutoff:   older than {days} days -> created before "
          f"{cutoff.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print()

    engine = make_engine(db_url)
    storage = build_storage(settings)

    try:
        # Select candidates (filter in Python too, to be robust to SQLite tz loss).
        async with session_scope(engine) as session:
            result = await session.exec(select(RunRow))
            all_runs = list(result.all())
        stale = [r for r in all_runs if _as_aware(r.created_at) < cutoff]

        if not stale:
            print("No runs older than the retention window. Nothing to do.")
            return 0

        print(f"{len(stale)} run(s) past the retention window:\n")
        _print_table(stale)
        print()

        if dry_run:
            print(f"DRY-RUN: would delete {len(stale)} run(s) and their artifacts. "
                  "Re-run with --apply to delete.")
            return len(stale)

        # --- apply: delete artifacts, then rows --------------------------- #
        total_files = 0
        deleted_ids: list[str] = []
        for r in stale:
            files = await _delete_artifacts(storage, r.id)
            total_files += files
            deleted_ids.append(r.id)
            print(f"  deleted artifacts for {r.id} ({files} file(s))")

        async with session_scope(engine) as session:
            result = await session.exec(
                select(RunRow).where(RunRow.id.in_(deleted_ids))
            )
            for row in result.all():
                await session.delete(row)

        print(f"\nDeleted {len(deleted_ids)} run(s) and {total_files} artifact file(s).")
        return len(deleted_ids)
    finally:
        await engine.dispose()


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete run data (artifacts + rows) older than N days. "
                    "Dry-run by default; pass --apply to actually delete.",
    )
    parser.add_argument("--days", type=int, default=90,
                        help="retention window in days (default: 90)")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                        help="report only, delete nothing (DEFAULT)")
    parser.add_argument("--apply", dest="apply", action="store_true",
                        help="actually delete (turns off the default dry-run)")
    parser.add_argument("--force-dev", dest="force_dev", action="store_true",
                        help="allow running against a SQLite URL (tests/local); "
                             "the repo ghostpanel.db is refused regardless")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    dry_run = not args.apply  # --apply overrides the dry-run default
    count = asyncio.run(run_retention(
        days=args.days, dry_run=dry_run, force_dev=args.force_dev,
    ))
    return 1 if count < 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
