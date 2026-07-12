#!/usr/bin/env bash

source /opt/wrolpi/wrolpi/scripts/lib.sh

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

DB_FILE=/media/wrolpi/config/wrolpi.db

if [ -f "${DB_FILE}" ]; then
  yes_or_no "Are you sure you want to reset the API database? All data will be lost." || exit 0
fi

set -x

systemctl stop wrolpi-api

# Delete the SQLite database (and its WAL sidecars), if it exists.
rm -f "${DB_FILE}" "${DB_FILE}-wal" "${DB_FILE}-shm"

# Recreate the database, run all migrations.
sudo -iu wrolpi /bin/bash -c 'cd /opt/wrolpi && /opt/wrolpi/venv/bin/python3 main.py db upgrade'

systemctl start wrolpi-api
