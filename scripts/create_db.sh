#!/usr/bin/env bash

# Create WROLPi API database.
sudo -u postgres psql -c '\l' | grep wrolpi || (
  sudo -u postgres createuser wrolpi
  sudo -u postgres psql -c "alter user postgres password 'wrolpi'"
  sudo -u postgres psql -c "alter user wrolpi password 'wrolpi'"
  sudo -u postgres createdb -E UTF8 -O wrolpi wrolpi
  echo "Created wrolpi database"
)
sudo -u wrolpi /bin/bash -c 'cd /opt/wrolpi && ./main.py db upgrade'

# Create gis (map) database.
sudo -u postgres psql -c '\l' | grep gis || (
  sudo -u postgres createdb -E UTF8 -O wrolpi gis
  sudo -u postgres psql -d gis -c "CREATE EXTENSION postgis"
  sudo -u postgres psql -d gis -c "CREATE EXTENSION hstore"
  sudo -u postgres psql -d gis -c "ALTER TABLE geometry_columns OWNER TO wrolpi"
  sudo -u postgres psql -d gis -c "ALTER TABLE spatial_ref_sys OWNER TO wrolpi"
  echo "Created gis database"
)
zcat /opt/wrolpi-blobs/gis-map.dump.gz | sudo -u postgres pg_restore --clean --no-owner -d gis
