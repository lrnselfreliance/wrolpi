#! /usr/bin/env bash
# Install and configure Renderd for Open Street Map.
set -e
set -x

# Initialize gis database.
if [ ! -d /opt/openstreetmap-carto ]; then
    git clone https://github.com/lrnselfreliance/openstreetmap-carto.git /opt/openstreetmap-carto
fi
(cd /opt/openstreetmap-carto && git fetch && git checkout master && git reset --hard origin/master && git pull --ff)
chown -R ${FIRST_USER_NAME}:${FIRST_USER_NAME} /opt/openstreetmap-carto
cd /opt/openstreetmap-carto
if [[ ! -f /opt/openstreetmap-carto/mapnik.xml || ! -s /opt/openstreetmap-carto/mapnik.xml ]]; then
  /usr/bin/carto project.mml >/opt/openstreetmap-carto/mapnik.xml
fi

# Configure renderd.
cp /opt/wrolpi/etc/debian11/renderd.conf /etc/renderd.conf
# Configure Apache2 to listen on 8084.
cp /opt/wrolpi/etc/debian11/ports.conf /etc/apache2/ports.conf
cp /opt/wrolpi/etc/debian11/000-default.conf /etc/apache2/sites-available/000-default.conf
# Copy Leaflet files to Apache's directory so they can be used offline.
cp /opt/wrolpi/etc/debian11/index.html \
  /opt/wrolpi/modules/map/leaflet.js \
  /opt/wrolpi/modules/map/leaflet.css /var/www/html/
chmod 644 /var/www/html/*

# mod_tile needs to be accessbile to renderd.
[ ! -d /var/lib/mod_tile ] && mkdir /var/lib/mod_tile
chown -R _renderd:_renderd /var/lib/mod_tile

# Enable mod-tile.
/usr/sbin/a2enconf mod_tile

