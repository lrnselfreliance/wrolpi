#! /usr/bin/env bash
# This script installs OpenStreetMap tile server.
# This server uses Apache2, renderd, and mod_tile to render and display map tiles.

source /opt/wrolpi/wrolpi/scripts/lib.sh

set -x
set -e

/opt/wrolpi/scripts/reset_map.sh

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
systemctl stop renderd
systemctl start renderd

systemctl stop apache2
systemctl start apache2
