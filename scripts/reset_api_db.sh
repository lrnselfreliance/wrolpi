#!/usr/bin/env bash

source /opt/wrolpi/wrolpi/scripts/lib.sh

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

if psql -l 2>/dev/null | grep wrolpi >/dev/null; then
  yes_or_no "Are you sure you want to reset the API database? All data will be lost." || exit 0
fi

set -x

systemctl stop wrolpi-api

# Delete the WROLPi API DB, if it exists.
sudo -iu postgres dropdb wrolpi
sudo -iu postgres dropuser wrolpi

/bin/bash /opt/wrolpi/scripts/initialize_api_db.sh
