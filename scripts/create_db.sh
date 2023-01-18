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
  sudo -u postgres createuser wrolpi
  sudo -u postgres createdb -E UTF8 -O wrolpi gis
  sudo -u postgres psql -d gis -c "CREATE EXTENSION postgis"
  sudo -u postgres psql -d gis -c "CREATE EXTENSION hstore"
  echo "Created gis database"
)
# Restore initial dump.
zcat /opt/wrolpi-blobs/gis-map.dump.gz | sudo -u wrolpi pg_restore --no-owner --role=wrolpi -d gis
sudo -u postgres psql gis -c 'ALTER TABLE geography_columns OWNER TO wrolpi'
sudo -u postgres psql -d gis -c "ALTER TABLE spatial_ref_sys OWNER TO wrolpi"
# Restore ownership of map files.
sudo chown -R wrolpi:wrolpi /var/lib/mod_tile /run/renderd
# Clear map tile cache files.
[ -d /var/lib/mod_tile/ajt ] && sudo rm -r /var/lib/mod_tile/ajt
