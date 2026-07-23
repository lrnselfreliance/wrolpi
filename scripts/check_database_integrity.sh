#!/usr/bin/env bash
# Check the integrity of the WROLPi SQLite database.
#
# A full integrity scan reads and verifies every page of the database, so it can
# take many minutes on a large DB or a slow (e.g. USB spinning) disk.  For that
# reason this is a standalone script rather than part of help.sh's quick startup
# diagnostics.
#
# Usage:
#   check_database_integrity.sh [--full] [DB_FILE]
#
#   --full       Run the exhaustive `PRAGMA integrity_check` (slower, checks
#                indexes as well).  The default is `PRAGMA quick_check`.
#   DB_FILE      Path to the database.  Defaults to
#                /media/wrolpi/config/wrolpi.db (override with WROLPI_DB env).

set -o pipefail

MEDIA_DIRECTORY=${MEDIA_DIRECTORY:-/media/wrolpi}

# Re-execute this script under sudo if not already root.  Reading a WAL database
# needs write access to the -shm sidecar; we run sqlite3 as the wrolpi user so we
# do not create root-owned sidecar files that would break the API.  Preserve the
# database overrides, since sudo strips them from the environment by default.
if [ "$EUID" != 0 ]; then
  exec sudo MEDIA_DIRECTORY="${MEDIA_DIRECTORY}" WROLPI_DB="${WROLPI_DB:-}" "$0" "$@"
fi

PRAGMA='quick_check'
DB_FILE=${WROLPI_DB:-${MEDIA_DIRECTORY}/config/wrolpi.db}
db_file_set=false

while [ $# -gt 0 ]; do
  case "$1" in
    --full|-f)
      PRAGMA='integrity_check'
      shift
      ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    -*)
      echo "FAILED: Unknown option: $1" >&2
      grep '^#' "$0" | sed 's/^# \{0,1\}//' >&2
      exit 2
      ;;
    *)
      if [ "${db_file_set}" = true ]; then
        echo "FAILED: Unexpected extra argument: $1" >&2
        grep '^#' "$0" | sed 's/^# \{0,1\}//' >&2
        exit 2
      fi
      DB_FILE=$1
      db_file_set=true
      shift
      ;;
  esac
done

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "FAILED: sqlite3 CLI is not installed"
  exit 2
fi

if [ ! -f "${DB_FILE}" ]; then
  echo "FAILED: Unable to find database at ${DB_FILE}"
  exit 2
fi

# Prefer running as the wrolpi user (owner of the DB / WAL sidecars); fall back to
# running directly if that user does not exist.
run_sqlite() {
  if id -u wrolpi >/dev/null 2>&1; then
    sudo -u wrolpi sqlite3 "${DB_FILE}" "$@"
  else
    sqlite3 "${DB_FILE}" "$@"
  fi
}

size=$(du -h "${DB_FILE}" 2>/dev/null | cut -f1)
echo "Checking ${DB_FILE} (${size:-unknown size}) with PRAGMA ${PRAGMA} ..."
echo "This reads the entire database and may take a while.  Please wait."

start=$(date +%s)
result=$(run_sqlite "PRAGMA ${PRAGMA};")
status=$?
elapsed=$(( $(date +%s) - start ))

if [ "${status}" != 0 ]; then
  echo "FAILED: sqlite3 could not read the database (exit ${status}) after ${elapsed}s"
  [ -n "${result}" ] && echo "${result}"
  exit 1
fi

if [ "$(printf '%s\n' "${result}" | head -1)" = "ok" ]; then
  echo "OK: Database passed ${PRAGMA} in ${elapsed}s"
  exit 0
else
  echo "FAILED: Database is corrupt (${PRAGMA}) after ${elapsed}s:"
  printf '%s\n' "${result}"
  exit 1
fi
