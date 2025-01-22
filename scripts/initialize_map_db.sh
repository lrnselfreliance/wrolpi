#!/usr/bin/env bash
# Creates the gis (map) database and _renderd database user if they don't exist.
# WARNING: This will overwrite the map database data.

source /opt/wrolpi/wrolpi/scripts/lib.sh

sudo -iu postgres psql -c '\l' 2>/dev/null | grep gis >/dev/null && (
  yes_or_no "Are you sure you want to initialize the map database?  Data from imported maps will be lost." || exit 0
)

set -x

systemctl stop renderd

# Create map database if it does not exist.
pg_createcluster 15 map --port=5433 --start -e utf8

# Create gis (map) database.
sudo -iu postgres psql -c '\l' --port=5433 | grep gis || (
  sudo -iu postgres createuser --port=5433 _renderd
  sudo -iu postgres psql --port=5433 -c "alter user _renderd password 'wrolpi'"
  sudo -iu postgres createdb --port=5433 -E UTF8 -O _renderd gis
  sudo -iu postgres psql -d gis --port=5433 -c 'CREATE EXTENSION postgis'
  sudo -iu postgres psql -d gis --port=5433 -c 'CREATE EXTENSION hstore'
  echo "Created gis database"
)
# Restore initial dump.
sudo -iu postgres pg_restore --port=5433 --no-owner --role=_renderd -d gis -j3 /opt/wrolpi-blobs/map-db-gis.dump
sudo -iu postgres psql --port=5433 -d gis -c 'ALTER TABLE geography_columns OWNER TO _renderd'
sudo -iu postgres psql --port=5433 -d gis -c 'ALTER TABLE geometry_columns OWNER TO _renderd'
sudo -iu postgres psql --port=5433 -d gis -c 'ALTER TABLE spatial_ref_sys OWNER TO _renderd'

# Clear map tile cache files.
yes | /bin/bash /opt/wrolpi/scripts/clear_map_cache.sh
