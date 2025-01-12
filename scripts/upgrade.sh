#! /usr/bin/env bash
# Installs any new dependencies of the App and API.  Uses internet.

set -e
set -x

# Install any App dependencies.
cd /opt/wrolpi/app || exit 1
npm install || npm install || npm install || npm install # try install multiple times  :(

# Install any new Python requirements.
/opt/wrolpi/venv/bin/pip3 install --upgrade -r /opt/wrolpi/requirements.txt
# Upgrade the WROLPi database.
(cd /opt/wrolpi && /opt/wrolpi/venv/bin/python3 /opt/wrolpi/main.py db upgrade)

# Upgrade WROLPi Help.
/opt/wrolpi/scripts/install_help_service.sh || echo "Help install failed."

# Get map db blob, if it is missing.
MAP_DB_BLOB=/opt/wrolpi-blobs/map-db-gis.dump
if [[ ! -f ${MAP_DB_BLOB} || ! -s ${MAP_DB_BLOB} ]]; then
  echo "Downloading new map blob (1.2 GB)..."
  wget https://wrolpi.nyc3.cdn.digitaloceanspaces.com/map-db-gis.dump -O ${MAP_DB_BLOB}
fi
if [[ -f /opt/wrolpi-blobs/gis-map.dump.gz && -s ${MAP_DB_BLOB} ]]; then
  # Remove old blob now that we have the new one.
  rm /opt/wrolpi-blobs/gis-map.dump.gz
fi

# Migrate map DB if necessary.  Do this before repair because it will reset map if map db is empty.
/opt/wrolpi/wrolpi/scripts/migrate_map_db.sh || echo "Map DB migration failed."

# Install any configs, restart services.
/opt/wrolpi/repair.sh
