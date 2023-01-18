#! /usr/bin/env bash
# Install and configure Renderd for Open Street Map.
set -e
set -x

# Create mapnik config.
if [ ! -d /opt/openstreetmap-carto ]; then
    git clone https://github.com/lrnselfreliance/openstreetmap-carto.git /opt/openstreetmap-carto
fi
(cd /opt/openstreetmap-carto && git fetch && git checkout master && git reset --hard origin/master && git pull --ff)
chown -R ${FIRST_USER_NAME}:${FIRST_USER_NAME} /opt/openstreetmap-carto
cd /opt/openstreetmap-carto
if [[ ! -f /opt/openstreetmap-carto/mapnik.xml || ! -s /opt/openstreetmap-carto/mapnik.xml ]]; then
  /usr/bin/carto project.mml >/opt/openstreetmap-carto/mapnik.xml
fi

# WROLPi user can access WROLPi and Map database.
cat > /home/wrolpi/.pgpass << 'EOF'
127.0.0.1:5432:gis:_renderd:wrolpi
127.0.0.1:5432:wrolpi:wrolpi:wrolpi
EOF
chmod 0600 /home/wrolpi/.pgpass

# Configure renderd.
cp /opt/wrolpi/etc/debian11/renderd.conf /etc/renderd.conf
# Configure Apache2 to listen on 8084.  Import renderd into apache.
cp /opt/wrolpi/etc/debian11/ports.conf /etc/apache2/ports.conf
cp /opt/wrolpi/etc/debian11/000-default.conf /etc/apache2/sites-available/000-default.conf
cp /opt/wrolpi/etc/ubuntu20.04/mod_tile.conf /etc/apache2/conf-enabled/mod_tile.conf
# Copy Leaflet files to Apache's directory so they can be used offline.
cp /opt/wrolpi/etc/debian11/index.html \
  /opt/wrolpi/modules/map/leaflet.js \
  /opt/wrolpi/modules/map/leaflet.css /var/www/html/
chmod 644 /var/www/html/*

mkdir /var/lib/mod_tile
chown -R _renderd:_renderd /var/lib/mod_tile
