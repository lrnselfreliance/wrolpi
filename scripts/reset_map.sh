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

# Initialize gis database.
[ -d /opt/openstreetmap-carto ] && chown -R wrolpi:wrolpi /opt/openstreetmap-carto
git clone https://github.com/lrnselfreliance/openstreetmap-carto.git /opt/openstreetmap-carto || :
chown -R _renderd:_renderd /opt/openstreetmap-carto
sudo -u _renderd /bin/bash -c '(cd /opt/openstreetmap-carto && git fetch && git checkout master && git reset --hard origin/master && git pull --ff)'
if [[ ! -f /opt/openstreetmap-carto/mapnik.xml || ! -s /opt/openstreetmap-carto/mapnik.xml ]]; then
  (cd /opt/openstreetmap-carto && carto project.mml >/opt/openstreetmap-carto/mapnik.xml)
fi
chown -R _renderd:_renderd /opt/openstreetmap-carto

# Reset map.  Force it.
/opt/wrolpi/scripts/reset_map.sh -f

cp /opt/wrolpi/etc/raspberrypios/renderd.conf /etc/renderd.conf
# Enable mod_tile.
cp /opt/wrolpi/etc/raspberrypios/mod_tile.conf /etc/apache2/conf-available/mod_tile.conf

/usr/sbin/a2enconf mod_tile

set +x

echo "Map has been reset."
