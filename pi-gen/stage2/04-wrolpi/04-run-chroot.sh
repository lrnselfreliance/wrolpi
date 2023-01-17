#! /usr/bin/env bash
# Install and configure Renderd for Open Street Map.
set -e
set -x

[ ! -d /var/lib/mod_tile ] && mkdir /var/lib/mod_tile
chown -R _renderd:_renderd /var/lib/mod_tile

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

cat > /etc/renderd.conf << 'EOF'
[renderd]
stats_file=/run/renderd/renderd.stats
socketname=/run/renderd/renderd.sock
num_threads=4
tile_dir=/var/cache/renderd/tiles

[mapnik]
plugins_dir=/usr/lib/mapnik/3.1/input
font_dir=/usr/share/fonts/truetype
font_dir_recurse=true

[ajt]
URI=/hot/
TILEDIR=/var/lib/mod_tile
XML=/opt/openstreetmap-carto/mapnik.xml
HOST=localhost
TILESIZE=256
MAXZOOM=20
EOF

cp /opt/wrolpi/etc/ubuntu20.04/mod_tile.conf /etc/apache2/conf-available/mod_tile.conf
cp /opt/wrolpi/modules/map/leaflet.js /var/www/html/leaflet.js
cp /opt/wrolpi/modules/map/leaflet.css /var/www/html/leaflet.css
cp /opt/wrolpi/etc/ubuntu20.04/ports.conf /etc/apache2/ports.conf
cp /opt/wrolpi/etc/ubuntu20.04/000-default.conf /etc/apache2/sites-available/000-default.conf
cp /opt/wrolpi/etc/ubuntu20.04/index.html /var/www/html/index.html

# Enable mod-tile.
/usr/sbin/a2enconf mod_tile

