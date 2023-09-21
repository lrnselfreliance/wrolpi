#!/usr/bin/env bash

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

/opt/wrolpi/scripts/initialize_api_db.sh
/opt/wrolpi/scripts/initialize_map_db.sh
