#! /usr/bin/env bash
# Install and configure Renderd for Open Street Map.
set -e
set -x

# Create mapnik config.
git clone https://github.com/lrnselfreliance/openstreetmap-carto.git /opt/openstreetmap-carto
git config --global --add safe.directory /opt/openstreetmap-carto
(cd /opt/openstreetmap-carto && git fetch && git checkout master && git reset --hard origin/master && git pull --ff)
chown -R wrolpi:wrolpi /opt/openstreetmap-carto
(cd /opt/openstreetmap-carto && carto project.mml >/opt/openstreetmap-carto/mapnik.xml)

# WROLPi user can access WROLPi and Map database.
mkdir -p /home/pi/Desktop
cat >/home/pi/.pgpass <<'EOF'
127.0.0.1:5432:gis:_renderd:wrolpi
127.0.0.1:5432:wrolpi:wrolpi:wrolpi
EOF
cat >/home/pi/Desktop/wrolpi.desktop <<'EOF'
[Desktop Entry]
Encoding=UTF-8
Name=WROLPi App
Type=Link
URL=http://127.0.0.1
Icon=/opt/wrolpi/icon.png
EOF
cat >/home/pi/Desktop/wrolpi-help.desktop <<'EOF'
[Desktop Entry]
Encoding=UTF-8
Name=WROLPi Help
Type=Link
URL=http://127.0.0.1:8086
Icon=/opt/wrolpi-help/venv/lib/python3.11/site-packages/mkdocs/themes/mkdocs/img/favicon.ico
EOF
chown -R pi:pi /home/pi
chmod 0600 /home/pi/.pgpass
usermod -aG wrolpi pi

# Configure renderd.
cp /opt/wrolpi/etc/raspberrypios/renderd.conf /etc/renderd.conf
# Configure Apache2 to listen on 8084.  Import renderd into apache.
cp /opt/wrolpi/etc/raspberrypios/ports.conf /etc/apache2/ports.conf
cp /opt/wrolpi/etc/raspberrypios/000-default.conf /etc/apache2/sites-available/000-default.conf
cp /opt/wrolpi/etc/raspberrypios/mod_tile.conf /etc/apache2/conf-enabled/mod_tile.conf
# Copy Leaflet files to Apache's directory so they can be used offline.
cp /opt/wrolpi/etc/raspberrypios/index.html \
  /opt/wrolpi/modules/map/leaflet.js \
  /opt/wrolpi/modules/map/leaflet.css /var/www/html/
chmod 644 /var/www/html/*

# Allow wrolpi user to delete map tiles.
usermod -aG _renderd wrolpi

[ ! -d /var/cache/renderd/tiles ] && mkdir /var/cache/renderd/tiles
chown -R _renderd:_renderd /var/cache/renderd/tiles

# Install WROLPi Help.
/opt/wrolpi/scripts/install_help_service.sh

# Create the media directory for the wrolpi user.
echo '/dev/sda1 /media/wrolpi auto defaults,nofail 0 0' | tee -a /etc/fstab
mkdir -p /media/wrolpi
cat >/home/wrolpi/.pgpass <<'EOF'
127.0.0.1:5432:gis:_renderd:wrolpi
127.0.0.1:5432:wrolpi:wrolpi:wrolpi
EOF
chmod 0600 /home/wrolpi/.pgpass
chown -R wrolpi:wrolpi /media/wrolpi /home/wrolpi /opt/wrolpi*

set +x

echo
echo "======================================================================"
echo "04-run-chroot.sh completed"
echo "======================================================================"
echo
