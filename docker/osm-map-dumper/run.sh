#!/bin/bash
# Taken from https://github.com/Overv/openstreetmap-tile-server and modified.

set -euo pipefail

function createPostgresConfig() {
  cp /etc/postgresql/14/main/postgresql.custom.conf.tmpl /etc/postgresql/14/main/conf.d/postgresql.custom.conf
  # shellcheck disable=SC2024
  sudo -u postgres echo "autovacuum = $AUTOVACUUM" >>/etc/postgresql/14/main/conf.d/postgresql.custom.conf
}

function setPostgresPassword() {
  sudo -u postgres psql -c "ALTER USER renderer PASSWORD '${PGPASSWORD:-renderer}'" >/dev/null
}

if [ -d /data/region.osm.pbf ]; then
  echo >&2 "ERROR: Found directory at /data/region.osm.pbf.  Did you mount the PBF file correctly?"
  exit 2
fi

if [ ! -f /data/region.osm.pbf ]; then
  echo >&2 "WARNING: No import file at /data/region.osm.pbf."
  echo >&2 "   Mount it: -v /absolute/path/to/your.osm.pbf:/data/region.osm.pbf"
  exit 3
fi

# if there is no custom style mounted, then use osm-carto
if [ ! "$(ls -A /data/style/)" ]; then
  mv /home/renderer/src/openstreetmap-carto-backup/* /data/style/
fi

# carto build
if [ ! -f /data/style/mapnik.xml ]; then
  cd /data/style/
  carto ${NAME_MML:-project.mml} >mapnik.xml
fi

# Ensure that database directory is in right state
mkdir -p /data/database/postgres/
chown renderer: /data/database/
chown -R postgres: /var/lib/postgresql /data/database/postgres/
if [ ! -f /data/database/postgres/PG_VERSION ]; then
  sudo -u postgres /usr/lib/postgresql/14/bin/pg_ctl -D /data/database/postgres/ initdb -o "--locale C.UTF-8" >/dev/null
fi

# Initialize PostgreSQL
echo >&2 "Initializing map tables"
createPostgresConfig
service postgresql start >/dev/null
sudo -u postgres createuser renderer >/dev/null
sudo -u postgres createdb -E UTF8 -O renderer gis >/dev/null
sudo -u postgres psql -d gis -c "CREATE EXTENSION postgis;" >/dev/null
sudo -u postgres psql -d gis -c "CREATE EXTENSION hstore;" >/dev/null
sudo -u postgres psql -d gis -c "ALTER TABLE geometry_columns OWNER TO renderer;" >/dev/null
sudo -u postgres psql -d gis -c "ALTER TABLE spatial_ref_sys OWNER TO renderer;" >/dev/null
setPostgresPassword

# copy polygon file if available
if [ -f /data/region.poly ]; then
  cp /data/region.poly /data/database/region.poly
  chown renderer: /data/database/region.poly
fi

# Import data
echo >&2 "Importing your map data"
sudo -u renderer osm2pgsql -d gis --create --slim -G --hstore \
  --tag-transform-script /data/style/${NAME_LUA:-openstreetmap-carto.lua} \
  --number-processes ${THREADS:-4} \
  -S /data/style/${NAME_STYLE:-openstreetmap-carto.style} \
  /data/region.osm.pbf \
  ${OSM2PGSQL_EXTRA_ARGS:-} \
  >/dev/null

# Create indexes
if [ -f /data/style/${NAME_SQL:-indexes.sql} ]; then
  sudo -u postgres psql -d gis -f /data/style/${NAME_SQL:-indexes.sql} >/dev/null
fi

# Import external data
echo >&2 "Importing planetary data"
chown -R renderer: /home/renderer/src/ /data/style/
if [ -f /data/style/scripts/get-external-data.py ] && [ -f /data/style/external-data.yml ]; then
  sudo -E -u renderer python3 /data/style/scripts/get-external-data.py \
    -c /data/style/external-data.yml -D /data/style/data >/dev/null
fi

echo >&2 "Dumping the DB"
sudo -u postgres pg_dump \
  --create \
  --clean \
  --format custom \
  --compress 9 \
  --no-owner \
  --no-comments \
  --encoding UTF-8 \
  --dbname gis

service postgresql stop
