#! /usr/bin/env bash
# This script installs OpenStreetMap tile server.
# This server uses Apache2, renderd, and mod_tile to render and display map tiles.

set -x
set -e

# Update if we haven't updated in the last day.
[ -z "$(find -H /var/lib/apt/lists -maxdepth 0 -mtime -1)" ] && apt update
# Install map dependencies.
apt install -y libapache2-mod-tile libboost-all-dev git tar unzip wget bzip2 build-essential autoconf libtool libxml2-dev libgeos-dev \
  libgeos++-dev libpq-dev libbz2-dev libproj-dev protobuf-c-compiler libfreetype6-dev libtiff5-dev \
  libicu-dev libgdal-dev libcairo2-dev libcairomm-1.0-dev libagg-dev liblua5.2-dev ttf-unifont lua5.1 liblua5.1-0-dev \
  postgis postgresql-13-postgis-3 postgresql-13-postgis-3-scripts osm2pgsql gdal-bin libmapnik-dev mapnik-utils \
  python3-mapnik apache2 apache2-dev libcurl4-gnutls-dev libiniparser-dev libmemcached-dev librados-dev \
  fonts-noto-cjk fonts-noto-hinted fonts-noto-unhinted postgresql-contrib osmium-tool python3-psycopg2 python3-yaml

/usr/bin/npm install -g carto@1.2.0
carto -v

# Create `gis` database for map.
sudo -u postgres psql -c '\l' | grep gis || (
  sudo -u postgres createuser _renderd || :
  sudo -u postgres psql -c "alter user _renderd password 'wrolpi'" || :
  sudo -u postgres createdb -E UTF8 -O _renderd gis
  sudo -u postgres psql -d gis -c "CREATE EXTENSION postgis" || :
  sudo -u postgres psql -d gis -c "CREATE EXTENSION hstore" || :
  echo "Created gis database"
)
sudo -u postgres psql -d gis -c 'ALTER TABLE geography_columns OWNER TO _renderd'
sudo -u postgres psql -d gis -c 'ALTER TABLE geometry_columns OWNER TO _renderd'
sudo -u postgres psql -d gis -c "ALTER TABLE spatial_ref_sys OWNER TO _renderd"

# Install Raspberry Pi OS compatible mod_tile.
git clone -b switch2osm https://github.com/lrnselfreliance/mod_tile.git /tmp/mod_tile || :
# Install init/systemd config to start map service on startup.
cp /opt/wrolpi/etc/raspberrypios/renderd /etc/init.d/renderd
sudo chmod +x /etc/init.d/renderd
cp /tmp/mod_tile/debian/renderd.service /lib/systemd/system/
chmod +x /etc/init.d/renderd

# Initialize gis database.
[ -d /opt/openstreetmap-carto ] && chown -R wrolpi:wrolpi /opt/openstreetmap-carto
git clone https://github.com/lrnselfreliance/openstreetmap-carto.git /opt/openstreetmap-carto || :
chown -R _renderd:_renderd /opt/openstreetmap-carto
sudo -u _renderd /bin/bash -c '(cd /opt/openstreetmap-carto && git fetch && git checkout master && git reset --hard origin/master && git pull --ff)'
cd /opt/openstreetmap-carto
if [[ ! -f /opt/openstreetmap-carto/mapnik.xml || ! -s /opt/openstreetmap-carto/mapnik.xml ]]; then
  carto project.mml >/opt/openstreetmap-carto/mapnik.xml
fi
chown -R _renderd:_renderd /opt/openstreetmap-carto

# Reset map.  Force it.
/opt/wrolpi/scripts/reset_map.sh -f

cp /opt/wrolpi/etc/raspberrypios/renderd.conf /etc/renderd.conf
# Enable mod_tile.
cp /opt/wrolpi/etc/raspberrypios/mod_tile.conf /etc/apache2/conf-available/mod_tile.conf

/usr/sbin/a2enconf mod_tile

# Configure Apache2 to listen on 8084.
cp /opt/wrolpi/etc/raspberrypios/ports.conf /etc/apache2/ports.conf
cp /opt/wrolpi/etc/raspberrypios/000-default.conf /etc/apache2/sites-available/000-default.conf
# Copy Leaflet files to Apache's directory so they can be used offline.
cp /opt/wrolpi/etc/raspberrypios/index.html \
  /opt/wrolpi/modules/map/leaflet.js \
  /opt/wrolpi/modules/map/leaflet.css /var/www/html/
chmod 644 /var/www/html/*

systemctl enable renderd
systemctl stop renderd
systemctl start renderd

systemctl stop apache2
systemctl start apache2
