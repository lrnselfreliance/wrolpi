#!/usr/bin/env bash

source /opt/wrolpi/wrolpi/scripts/lib.sh

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

if psql -l 2>/dev/null | grep gis >/dev/null; then
  yes_or_no "Are you sure you want to delete the map database and cache?  This can't be undone!" || exit 0
fi

set -e
set -x

systemctl stop renderd

sudo -u postgres dropdb gis || :
sudo -u postgres dropuser _renderd || :

# Reset "imported" status of any map files.
sudo -u postgres psql -d wrolpi -c "UPDATE map_file SET imported=false"

yes | /opt/wrolpi/scripts/initialize_map_db.sh

set +x

echo "Map has been reset."
