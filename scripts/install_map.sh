#! /usr/bin/env bash
# This script installs OpenStreetMap tile server.
# This server uses Apache2, renderd, and mod_tile to render and display map tiles.

source /opt/wrolpi/wrolpi/scripts/lib.sh

set -x
set -e

systemctl stop renderd || :
systemctl stop apache2 || :

/opt/wrolpi/scripts/reset_map.sh

# Configure renderd.
[ -d /opt/openstreetmap-carto ] && chown -R wrolpi:wrolpi /opt/openstreetmap-carto
git clone https://github.com/lrnselfreliance/openstreetmap-carto.git /opt/openstreetmap-carto || :
chown -R _renderd:_renderd /opt/openstreetmap-carto
sudo -u _renderd /bin/bash -c '(cd /opt/openstreetmap-carto && git fetch && git checkout master && git reset --hard origin/master && git pull --ff)'
if [[ ! -f /opt/openstreetmap-carto/mapnik.xml || ! -s /opt/openstreetmap-carto/mapnik.xml ]]; then
  (cd /opt/openstreetmap-carto && carto project.mml >/opt/openstreetmap-carto/mapnik.xml)
fi
chown -R _renderd:_renderd /opt/openstreetmap-carto

cp /opt/wrolpi/etc/raspberrypios/renderd.conf /etc/renderd.conf
# Enable mod_tile.
cp /opt/wrolpi/etc/raspberrypios/mod_tile.conf /etc/apache2/conf-available/mod_tile.conf

/usr/sbin/a2enconf mod_tile

carto -v

cp /opt/wrolpi/etc/raspberrypios/renderd.conf /etc/renderd.conf
# Configure Apache2 to listen on 8084.
cp /opt/wrolpi/etc/raspberrypios/ports.conf /etc/apache2/ports.conf
if [[ ${rpi} == true ]]; then
  cp /opt/wrolpi/etc/raspberrypios/000-default.conf /etc/apache2/sites-available/000-default.conf
else
  cp /opt/wrolpi/etc/debian12/000-default.conf /etc/apache2/sites-available/000-default.conf
fi
# Copy Leaflet files to Apache's directory so they can be used offline.
cp /opt/wrolpi/etc/raspberrypios/index.html \
  /opt/wrolpi/modules/map/leaflet.js \
  /opt/wrolpi/modules/map/leaflet.css /var/www/html/
chmod 644 /var/www/html/*

systemctl enable renderd
systemctl start renderd
systemctl start apache2
