#!/usr/bin/env bash
# This script will attempt to repair a WROLPi installation.  It will not use internet.

cd /opt/wrolpi || (echo "Cannot repair.  /opt/wrolpi does not exist" && exit 1)

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

rpi=false
if (grep 'Raspberry Pi' /proc/cpuinfo >/dev/null); then
  rpi=true
fi

set -e
set -x

# Stop services if they are running.
systemctl stop wrolpi-api.service || :
systemctl stop wrolpi-app.service || :
systemctl stop wrolpi-kiwix.service || :
systemctl stop nginx || :
systemctl stop renderd || :
systemctl stop apache2 || :

# Reset any inadvertent changes to the WROLPi repo.
git config --global --add safe.directory /opt/wrolpi
git reset HEAD --hard

# Rebuild the app after reset.
(cd app && npm run build)

# Copy configs to system.
[ -f /etc/nginx/cert.key ] || openssl genrsa -out /etc/nginx/cert.key 2048
[ -f /etc/nginx/cert.crt ] || openssl req -new -x509 -nodes -key /etc/nginx/cert.key -out /etc/nginx/cert.crt \
  -days 3650 -subj "/C=US/ST=State/L=City/O=Org/OU=WROLPi/CN=wrolpi.local"
cp /opt/wrolpi/etc/raspberrypios/nginx.conf /etc/nginx/nginx.conf
cp /opt/wrolpi/etc/raspberrypios/wrolpi.conf /etc/nginx/wrolpi.conf
cp /opt/wrolpi/etc/raspberrypios/50x.html /var/www/50x.html

# WROLPi needs a few privileged commands.
cp /opt/wrolpi/etc/raspberrypios/90-wrolpi /etc/sudoers.d/90-wrolpi
chmod 0440 /etc/sudoers.d/90-wrolpi
# Verify this new file is valid.
visudo -c -f /etc/sudoers.d/90-wrolpi

# Install the systemd services
cp /opt/wrolpi/etc/raspberrypios/wrolpi*.service /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi.target /etc/systemd/system/
/usr/bin/systemctl daemon-reload
systemctl enable wrolpi-api.service
systemctl enable wrolpi-app.service
systemctl enable wrolpi-kiwix.service
systemctl enable wrolpi-help.service

cp /opt/wrolpi/etc/raspberrypios/renderd.conf /etc/renderd.conf
# Configure Apache2 to listen on 8084.
cp /opt/wrolpi/etc/raspberrypios/ports.conf /etc/apache2/ports.conf
cp /opt/wrolpi/etc/debian12/000-default.conf /etc/apache2/sites-available/000-default.conf
# Copy Leaflet files to Apache's directory so they can be used offline.
cp /opt/wrolpi/etc/raspberrypios/index.html \
  /opt/wrolpi/modules/map/leaflet.js \
  /opt/wrolpi/modules/map/leaflet.css /var/www/html/
chmod 644 /var/www/html/*

systemctl enable renderd
systemctl start renderd

# Create the WROLPi user
grep wrolpi: /etc/passwd || useradd -md /home/wrolpi wrolpi -s "$(command -v bash)"
[ -f /home/wrolpi/.pgpass ] || cat >/home/wrolpi/.pgpass <<'EOF'
127.0.0.1:5432:gis:_renderd:wrolpi
127.0.0.1:5432:wrolpi:wrolpi:wrolpi
EOF
chmod 0600 /home/wrolpi/.pgpass

# WROLPi needs a few privileged commands.
cp /opt/wrolpi/etc/raspberrypios/90-wrolpi /etc/sudoers.d/90-wrolpi
chmod 0440 /etc/sudoers.d/90-wrolpi
# Verify this new file is valid.
visudo -c -f /etc/sudoers.d/90-wrolpi

# Configure Postgresql.  Do this after the API is stopped.
/opt/wrolpi/scripts/initialize_api_db.sh
# wrolpi user is superuser so they can import maps.
sudo -u postgres psql -c "alter user wrolpi with superuser"

# Configure renderd.
if [ ! -d /opt/openstreetmap-carto ]; then
  echo "/opt/openstreetmap-carto does not exist!  Has install completed?" && exit 1
fi
chown -R _renderd:_renderd /opt/openstreetmap-carto
if [[ ! -f /opt/openstreetmap-carto/mapnik.xml || ! -s /opt/openstreetmap-carto/mapnik.xml ]]; then
  (cd /opt/openstreetmap-carto && carto project.mml >/opt/openstreetmap-carto/mapnik.xml)
fi
chown -R _renderd:_renderd /opt/openstreetmap-carto

cp /opt/wrolpi/etc/raspberrypios/renderd.conf /etc/renderd.conf
# Enable mod_tile.
cp /opt/wrolpi/etc/raspberrypios/mod_tile.conf /etc/apache2/conf-available/mod_tile.conf

carto -v

# Initialize the map if it has not been initialized.
sudo -u postgres psql -c '\l' | grep gis || /opt/wrolpi/scripts/initialize_map_db.sh

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

# Create the media directory.  This should be mounted by the maintainer.
[ -d /media/wrolpi ] || mkdir /media/wrolpi
chown wrolpi:wrolpi /media/wrolpi

chown -R wrolpi:wrolpi /home/wrolpi /opt/wrolpi*

systemctl restart wrolpi-help
systemctl start wrolpi.target

set +x

echo "Repair has completed.  You may run /opt/wrolpi/help.sh to check system status."
