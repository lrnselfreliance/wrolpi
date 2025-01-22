#! /usr/bin/env bash
# Install and configure Renderd for Open Street Map.
set -e
set -x

# Create postgres cluster for map.
pg_createcluster 15 map --port=5433 -e utf8

# Create mapnik config.
git clone https://github.com/lrnselfreliance/openstreetmap-carto.git /opt/openstreetmap-carto
git config --global --add safe.directory /opt/openstreetmap-carto
(cd /opt/openstreetmap-carto && git fetch && git checkout master && git reset --hard origin/master && git pull --ff)
chown -R wrolpi:wrolpi /opt/openstreetmap-carto
# Append port line after dbname configuration line.
sed -i '/dbname: "gis"/a \    port: 5433' /opt/openstreetmap-carto/project.mml
(cd /opt/openstreetmap-carto/ && carto project.mml >mapnik.xml)

# All users can access wrolpi and map database.
cat >/etc/skel/.pgpass <<'EOF'
127.0.0.1:5433:gis:_renderd:wrolpi
127.0.0.1:5432:wrolpi:wrolpi:wrolpi
EOF
chmod 0600 /etc/skel/.pgpass
cat >/etc/skel/.gitconfig  <<'EOF'
[safe]
	directory = /opt/wrolpi
	directory = /opt/wrolpi-help
EOF
# Copy desktop shortcuts.
mkdir /etc/skel/Desktop
cp /opt/wrolpi/etc/raspberrypios/*desktop /etc/skel/Desktop

# Configure renderd (map).
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
chown -R wrolpi:wrolpi /media/wrolpi /home/wrolpi /opt/wrolpi*

set +x

echo
echo "======================================================================"
echo "04-run-chroot.sh completed"
echo "======================================================================"
echo
