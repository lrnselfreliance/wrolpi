#!/usr/bin/env bash

source /opt/wrolpi/wrolpi/scripts/lib.sh

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

# Use 1/4 of the RAM to import.  1/2 causes crashes on RPi.
RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MAX_CACHE=$((RAM_KB / 1024 / 4))

yes_or_no "Are you sure you want to delete the map database and cache?  This can't be undone!" || exit 0

set -e
set -x

systemctl stop renderd

chown -R _renderd:_renderd /var/lib/mod_tile

sudo -u postgres dropdb gis || :
sudo -u postgres dropuser _renderd || :

# Reset "imported" status of any map files.
sudo -u postgres psql -d wrolpi -c "UPDATE map_file SET imported=false"

yes | bash "${PROJECT_DIR}/scripts/initialize_map_db.sh"

set +x

echo "Map has been reset."
