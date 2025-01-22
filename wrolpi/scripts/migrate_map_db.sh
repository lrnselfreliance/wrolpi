#! /usr/bin/env bash
# Moves the `gis` map from default database on 5432 to a new database on 5433.
# This script should only need to be run once.  If you are having issues with your map, try
# /opt/wrolpi/scripts/reset_map.sh

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

sudo -iu postgres psql -c '\l' --port=5433 2>/dev/null | grep -q gis && (
  echo "Map DB already migrated."
  exit 0
)

function cleanup() {
  if [ -e /tmp/map.dump ]; then
    rm -rf /tmp/map.dump
  fi
}

trap cleanup EXIT
cleanup

systemctl stop renderd

# Create new cluster for the map.
pg_createcluster 15 map --port=5433 --start -e utf8
# Disable JIT as recommended by mod_tile
sed -i 's/#jit =.*/jit = off/' /etc/postgresql/15/map/postgresql.conf

# Create user permissions for map user.
sudo -iu postgres psql -c '\l' --port=5433 | grep gis || (
  sudo -iu postgres createuser --port=5433 _renderd
  sudo -iu postgres psql --port=5433 -c "alter user _renderd password 'wrolpi'"
  sudo -iu postgres createdb --port=5433 -E UTF8 -O _renderd gis
  sudo -iu postgres psql -d gis --port=5433 -c 'CREATE EXTENSION postgis'
  sudo -iu postgres psql -d gis --port=5433 -c 'CREATE EXTENSION hstore'
)

# Override niceness of new map database.
cp -r /opt/wrolpi/etc/raspberrypios/postgresql@15-map.service.d /etc/systemd/system/
systemctl daemon-reload
systemctl restart postgresql@15-map.service

# Dump old DB, then restore in new DB.
>&2 echo "Dumping map database, this may take several hours if your map is large..."
sudo -iu postgres pg_dump -Fd gis --port=5432 -j3 -f /tmp/map.dump &&  # 5432 is old DB.
  sudo -iu postgres pg_restore --port=5433 -j3 -d gis /tmp/map.dump && # 5433 is new DB.
  sudo -iu postgres dropdb --port=5432 gis

# Update openstreetmap-carto to use the new database.
grep -q 'port: 5433' /opt/openstreetmap-carto/project.mml || (
  # Append port line after dbname configuration line.
  sed -i '/dbname: "gis"/a \    port: 5433' /opt/openstreetmap-carto/project.mml
  (cd /opt/openstreetmap-carto/ && carto project.mml >mapnik.xml)
)
