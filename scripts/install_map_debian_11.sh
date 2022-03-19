#! /usr/bin/bash
# This script installs OpenStreetMap tile server.
# This server uses Apache2, renderd and mod_tile to render and display map tiles.

set -x
set -e

# Update if we haven't updated in the last day.
[ -z "$(find -H /var/lib/apt/lists -maxdepth 0 -mtime -1)" ] && apt update
# Install map dependencies.
apt install -y libapache2-mod-tile renderd tar unzip wget bzip2 apache2 lua5.1 mapnik-utils python3-mapnik gdal-bin \
  fonts-noto-cjk fonts-noto-hinted fonts-noto-unhinted ttf-unifont

/usr/bin/npm install -g carto
/usr/local/bin/carto -v

# Create `gis` database for map.
sudo -u postgres psql -c '\l' | grep gis || sudo -u postgres createdb -E UTF8 -O wrolpi gis
sudo -u postgres psql -d gis -c "CREATE EXTENSION postgis;" || :
sudo -u postgres psql -d gis -c "CREATE EXTENSION hstore;" || :
sudo -u postgres psql -d gis -c "ALTER TABLE geometry_columns OWNER TO wrolpi;"
sudo -u postgres psql -d gis -c "ALTER TABLE spatial_ref_sys OWNER TO wrolpi;"

# Install Debian 11 compatible mod_tile.
git clone -b switch2osm https://github.com/lrnselfreliance/mod_tile.git /tmp/mod_tile || :
# Install init/systemd config to start map service on startup.
cp /tmp/mod_tile/debian/renderd.init /etc/init.d/renderd
sudo chmod +x /etc/init.d/renderd
sed -i -e 's/^RUNASUSER.*/RUNASUSER=wrolpi/' /etc/init.d/renderd
sed -i -e 's/^DAEMON=.*/DAEMON=\/usr\/bin\/$NAME/' /etc/init.d/renderd
sed -i -e 's/^DAEMON_ARGS=.*/DAEMON_ARGS="-c \/etc\/renderd.conf"/' /etc/init.d/renderd
cp /tmp/mod_tile/debian/renderd.service /lib/systemd/system/
chmod +x /etc/init.d/renderd
[ ! -d /var/lib/mod_tile ] && mkdir /var/lib/mod_tile
chown wrolpi /var/lib/mod_tile

# Initialize gis database.
git clone https://github.com/lrnselfreliance/openstreetmap-carto.git /opt/openstreetmap-carto || :
chown -R wrolpi:wrolpi /opt/openstreetmap-carto
cd /opt/openstreetmap-carto
if [[ ! -f /opt/openstreetmap-carto/mapnik.xml || ! -s /opt/openstreetmap-carto/mapnik.xml ]]; then
  /usr/local/bin/carto project.mml >/opt/openstreetmap-carto/mapnik.xml
fi
# Initialize indexes and global polygons.
sudo -u wrolpi /opt/openstreetmap-carto/scripts/get-external-data.py -d gis -U wrolpi
# Use D.C. to initialized DB because it is so small.
wget --continue https://download.geofabrik.de/north-america/us/district-of-columbia-latest.osm.pbf \
  -O /tmp/district-of-columbia-latest.osm.pbf
# Run import in "create" mode so basic tables will be created.
sudo -u wrolpi osm2pgsql -d gis --create --slim -G --hstore --tag-transform-script \
  /opt/openstreetmap-carto/openstreetmap-carto.lua -C 2000 --number-processes 4 \
  -S /opt/openstreetmap-carto/openstreetmap-carto.style /tmp/district-of-columbia-latest.osm.pbf
sudo -u wrolpi psql -d gis -f /opt/openstreetmap-carto/indexes.sql

cp /opt/wrolpi/etc/debian11/renderd.conf /etc/renderd.conf
# Configure Apache2 to listen on 8084.
cp /opt/wrolpi/etc/debian11/ports.conf /etc/apache2/ports.conf
cp /opt/wrolpi/etc/debian11/000-default.conf /etc/apache2/sites-available/000-default.conf
# Copy Leaflet files to Apache's directory so they can be used offline.
cp /opt/wrolpi/etc/debian11/index.html \
  /opt/wrolpi/modules/map/leaflet.js \
  /opt/wrolpi/modules/map/leaflet.css /var/www/html/
chmod 644 /var/www/html/*

systemctl enable renderd
systemctl stop renderd
systemctl start renderd

systemctl stop apache2
systemctl start apache2
