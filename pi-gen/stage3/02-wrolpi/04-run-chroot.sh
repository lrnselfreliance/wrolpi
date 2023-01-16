#! /usr/bin/env bash
# Install and configure Renderd for Open Street Map.
set -e
set -x

[ ! -d /var/lib/mod_tile ] && mkdir /var/lib/mod_tile
chown 1000:1000 /var/lib/mod_tile

# Initialize gis database.
if [ ! -d /opt/openstreetmap-carto ]; then
    git clone https://github.com/lrnselfreliance/openstreetmap-carto.git /opt/openstreetmap-carto
fi
(cd /opt/openstreetmap-carto && git fetch && git checkout master && git reset --hard origin/master && git pull --ff)
chown -R 1000:1000 /opt/openstreetmap-carto
cd /opt/openstreetmap-carto
if [[ ! -f /opt/openstreetmap-carto/mapnik.xml || ! -s /opt/openstreetmap-carto/mapnik.xml ]]; then
  /usr/bin/carto project.mml >/opt/openstreetmap-carto/mapnik.xml
fi

# Configure renderd.
cp /opt/wrolpi/etc/ubuntu20.04/renderd.conf /usr/local/etc/renderd.conf
# Enable mod-tile.
/usr/sbin/a2enconf mod_tile

# Swap renderd user to wrolpi.
cat > /usr/lib/systemd/system/renderd.service <<'EOF'
[Unit]
Description=Daemon that renders map tiles using mapnik
Documentation=man:renderd
After=network.target auditd.service

[Service]
ExecStart=/usr/bin/renderd -f
User=wrolpi

[Install]
WantedBy=multi-user.target
EOF

cp /opt/wrolpi/etc/ubuntu20.04/mod_tile.conf /etc/apache2/conf-available/mod_tile.conf
cp /opt/wrolpi/modules/map/leaflet.js /var/www/html/leaflet.js
cp /opt/wrolpi/modules/map/leaflet.css /var/www/html/leaflet.css
cp /opt/wrolpi/etc/ubuntu20.04/ports.conf /etc/apache2/ports.conf
cp /opt/wrolpi/etc/ubuntu20.04/000-default.conf /etc/apache2/sites-available/000-default.conf
cp /opt/wrolpi/etc/ubuntu20.04/index.html /var/www/html/index.html
