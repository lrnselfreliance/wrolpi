#!/usr/bin/env bash
# Creates the wrolpi database user and database if they don't exist.
# It is always safe to run this script.

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

set -x

# Create WROLPi API database.
sudo -u postgres psql -c '\l' | grep wrolpi || (
  sudo -u postgres createuser -s wrolpi  # superuser so maps can be imported
  sudo -u postgres psql -c "alter user postgres password 'wrolpi'"
  sudo -u postgres psql -c "alter user wrolpi password 'wrolpi'"
  sudo -u postgres createdb -E UTF8 -O wrolpi wrolpi
  echo "Created wrolpi database"
)
sudo -u wrolpi /bin/bash -c 'cd /opt/wrolpi && /opt/wrolpi/venv/bin/python3 main.py db upgrade'
