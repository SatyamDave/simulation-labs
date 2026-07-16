#!/usr/bin/env bash
#
# ops/backup.sh — logical backup of the Simulation Labs Postgres database.
#
# Runs pg_dump against $DATABASE_URL into a timestamped custom-format dump under
# $BACKUP_DIR, then (optionally, env-gated) uploads it to S3. Prints where it wrote.
#
# Env:
#   DATABASE_URL        (required) async or libpq URL, e.g.
#                       postgresql+asyncpg://user:pass@host:5432/simlabs
#                       (the +asyncpg / +psycopg driver suffix is stripped for pg_dump)
#   BACKUP_DIR          (default ./backups) local directory for the dump file
#   BACKUP_S3_BUCKET    (optional) if set, the dump is uploaded here after writing
#   BACKUP_S3_PREFIX    (default db-backups) key prefix within the bucket
#   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION  (S3 upload, read by awscli)
#   AWS_ENDPOINT_URL    (optional) for MinIO / S3-compatible endpoints
#
# Scheduling:
#   cron (daily 03:17 UTC):
#     17 3 * * *  cd /srv/simlabs && DATABASE_URL=... BACKUP_S3_BUCKET=... \
#                   bash ops/backup.sh >> /var/log/simlabs-backup.log 2>&1
#   GitHub Actions (scheduled workflow):
#     on:
#       schedule:
#         - cron: "17 3 * * *"     # daily 03:17 UTC
#     jobs:
#       backup:
#         runs-on: ubuntu-latest
#         steps:
#           - uses: actions/checkout@v4
#           - run: sudo apt-get update && sudo apt-get install -y postgresql-client awscli
#           - run: bash ops/backup.sh
#             env:
#               DATABASE_URL:     ${{ secrets.DATABASE_URL }}
#               BACKUP_S3_BUCKET: ${{ secrets.BACKUP_S3_BUCKET }}
#               AWS_ACCESS_KEY_ID:     ${{ secrets.AWS_ACCESS_KEY_ID }}
#               AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
#               AWS_REGION:            ${{ secrets.AWS_REGION }}
#
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be set (async or libpq Postgres URL)}"

# The app stores an async SQLAlchemy URL (postgresql+asyncpg://...). pg_dump speaks
# libpq, so strip the driver suffix.
PG_URL="${DATABASE_URL}"
PG_URL="${PG_URL/+asyncpg/}"
PG_URL="${PG_URL/+psycopg2/}"
PG_URL="${PG_URL/+psycopg/}"

case "${PG_URL}" in
  postgres://*|postgresql://*) : ;;
  *)
    echo "ERROR: DATABASE_URL is not a Postgres URL (got: ${PG_URL%%://*}://...)." >&2
    echo "       backup.sh only backs up Postgres; SQLite dev DBs are not backed up." >&2
    exit 1
    ;;
esac

BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "${BACKUP_DIR}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BACKUP_DIR}/simlabs-${TS}.dump"

echo "Backing up database -> ${OUT}"
# --format=custom => compressed, restorable selectively with pg_restore.
# --no-owner / --no-privileges => restorable into a differently-owned target DB.
pg_dump \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file="${OUT}" \
  --dbname="${PG_URL}"

SIZE="$(wc -c < "${OUT}" | tr -d ' ')"
echo "Wrote backup: ${OUT} (${SIZE} bytes)"

# Optional, env-gated upload to S3 / S3-compatible storage.
if [[ -n "${BACKUP_S3_BUCKET:-}" ]]; then
  PREFIX="${BACKUP_S3_PREFIX:-db-backups}"
  DEST="s3://${BACKUP_S3_BUCKET}/${PREFIX}/simlabs-${TS}.dump"
  ENDPOINT_ARG=()
  if [[ -n "${AWS_ENDPOINT_URL:-}" ]]; then
    ENDPOINT_ARG=(--endpoint-url "${AWS_ENDPOINT_URL}")
  fi
  echo "Uploading -> ${DEST}"
  aws "${ENDPOINT_ARG[@]}" s3 cp "${OUT}" "${DEST}"
  echo "Uploaded backup: ${DEST}"
else
  echo "BACKUP_S3_BUCKET not set; skipping S3 upload (local dump only)."
fi

echo "Backup complete."
