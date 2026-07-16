#!/usr/bin/env bash
#
# ops/restore.sh — restore a pg_dump into a target Postgres database.
#
# !!! DESTRUCTIVE !!!  This DROPS and recreates objects in the target database
# (pg_restore --clean --if-exists). Existing data in the target IS OVERWRITTEN.
# It refuses to run without a typed confirmation matching the target DB name.
#
# Usage:
#   ops/restore.sh <dump-file> [TARGET_DATABASE_URL]
#
# Env:
#   RESTORE_DATABASE_URL / DATABASE_URL  used as the target if no 2nd arg is given.
#   RESTORE_CONFIRM      (optional) preset the confirmation for non-interactive use
#                        (must equal the target database name). Use with care.
#
set -euo pipefail

DUMP="${1:?usage: ops/restore.sh <dump-file> [TARGET_DATABASE_URL]}"
TARGET_URL="${2:-${RESTORE_DATABASE_URL:-${DATABASE_URL:-}}}"

: "${TARGET_URL:?target DB URL required (2nd arg, RESTORE_DATABASE_URL, or DATABASE_URL)}"

if [[ ! -f "${DUMP}" ]]; then
  echo "ERROR: dump file not found: ${DUMP}" >&2
  exit 1
fi

# Normalize the async SQLAlchemy URL to a libpq URL for pg_restore.
PG_URL="${TARGET_URL}"
PG_URL="${PG_URL/+asyncpg/}"
PG_URL="${PG_URL/+psycopg2/}"
PG_URL="${PG_URL/+psycopg/}"

case "${PG_URL}" in
  postgres://*|postgresql://*) : ;;
  *)
    echo "ERROR: target is not a Postgres URL (got: ${PG_URL%%://*}://...)." >&2
    exit 1
    ;;
esac

# Best-effort parse of host + database name for the warning and confirmation prompt.
# Strip scheme, then userinfo, then split host/path.
_no_scheme="${PG_URL#*://}"
_hostpart="${_no_scheme##*@}"          # drop user:pass@ if present
_hostport="${_hostpart%%/*}"           # host:port
_dbpart="${_hostpart#*/}"              # dbname?query
DB_NAME="${_dbpart%%\?*}"              # strip ?sslmode=... etc.

if [[ -z "${DB_NAME}" || "${DB_NAME}" == "${_hostpart}" ]]; then
  echo "ERROR: could not parse a database name from the target URL." >&2
  exit 1
fi

echo "============================================================"
echo " DESTRUCTIVE RESTORE"
echo "   dump:   ${DUMP}"
echo "   target: host=${_hostport} db=${DB_NAME}"
echo ""
echo " This will DROP and recreate objects in the target database."
echo " All current data in '${DB_NAME}' will be OVERWRITTEN."
echo "============================================================"

CONFIRM="${RESTORE_CONFIRM:-}"
if [[ -z "${CONFIRM}" ]]; then
  # Read from the terminal even if stdin is piped, when a TTY is available.
  if [[ -r /dev/tty ]]; then
    printf 'Type the target database name (%s) to proceed: ' "${DB_NAME}" > /dev/tty
    read -r CONFIRM < /dev/tty
  else
    echo "ERROR: no TTY for confirmation and RESTORE_CONFIRM is unset; refusing." >&2
    exit 1
  fi
fi

if [[ "${CONFIRM}" != "${DB_NAME}" ]]; then
  echo "Confirmation did not match '${DB_NAME}'. Aborting; nothing was changed." >&2
  exit 1
fi

echo "Confirmed. Restoring ${DUMP} -> ${DB_NAME} ..."
# --clean --if-exists => drop existing objects first (idempotent-ish restore).
# --no-owner => don't require the dump's original roles to exist.
pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --dbname="${PG_URL}" \
  "${DUMP}"

echo "Restore complete."
