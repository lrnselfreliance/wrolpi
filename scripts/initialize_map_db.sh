#!/usr/bin/env bash
# Creates the gis (map) database and _renderd database user if they don't exist.

source /opt/wrolpi/wrolpi/scripts/lib.sh

yes_or_no "Are you sure you want to initialize the map database?  Data from imported maps will be lost." || exit 0

systemctl stop renderd

# Create gis (map) database.
sudo -u postgres psql -c '\l' | grep gis || (
  sudo -u postgres createuser _renderd
  sudo -u postgres psql -c "alter user _renderd password 'wrolpi'"
  sudo -u postgres createdb -E UTF8 -O _renderd gis
  sudo -u postgres psql -d gis -c "CREATE EXTENSION postgis"
  sudo -u postgres psql -d gis -c "CREATE EXTENSION hstore"
  echo "Created gis database"
)
# Restore initial dump.
zcat /opt/wrolpi-blobs/gis-map.dump.gz | sudo -u postgres pg_restore --no-owner --role=_renderd -d gis
sudo -u postgres psql -d gis -c 'ALTER TABLE geography_columns OWNER TO _renderd'
sudo -u postgres psql -d gis -c 'ALTER TABLE geometry_columns OWNER TO _renderd'
sudo -u postgres psql -d gis -c "ALTER TABLE spatial_ref_sys OWNER TO _renderd"
# Clear map tile cache files.
[ -d /var/cache/renderd/tiles/ajt ] && sudo rm -r /var/cache/renderd/tiles/ajt

systemctl start renderd
