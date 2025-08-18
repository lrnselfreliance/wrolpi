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

# Create the WROLPi user
grep wrolpi: /etc/passwd || useradd -md /home/wrolpi wrolpi -s "$(command -v bash)"
[ -f /home/wrolpi/.pgpass ] || cat >/home/wrolpi/.pgpass <<'EOF'
127.0.0.1:5433:gis:_renderd:wrolpi
127.0.0.1:5432:wrolpi:wrolpi:wrolpi
EOF
chmod 0600 /home/wrolpi/.pgpass

# Reset any inadvertent changes to the WROLPi repo.  Restore ownership in case this repair script fails.
git config --global --add safe.directory /opt/wrolpi
git reset HEAD --hard
chown -R wrolpi:wrolpi /opt/wrolpi

# Copy configs to system.
cp /opt/wrolpi/etc/raspberrypios/nginx.conf /etc/nginx/nginx.conf
[ -f /etc/nginx/conf.d/default.conf ] && rm /etc/nginx/conf.d/default.conf
cp /opt/wrolpi/etc/raspberrypios/wrolpi.conf /etc/nginx/conf.d/wrolpi.conf
cp /opt/wrolpi/etc/raspberrypios/50x.html /var/www/50x.html

# Generate nginx certificate for HTTPS.
if [[ ! -f /etc/nginx/cert.crt || ! -f /etc/nginx/cert.key ]]; then
  openssl genrsa -out /etc/nginx/cert.key 2048
  openssl req -new -x509 -nodes -key /etc/nginx/cert.key -out /etc/nginx/cert.crt -days 3650  \
      -subj "/C=US/ST=State/L=City/O=Org/OU=WROLPi/CN=$(hostname).local"
  chmod 640 /etc/nginx/cert.key /etc/nginx/cert.crt
fi

# WROLPi needs a few privileged commands.
cp /opt/wrolpi/etc/raspberrypios/90-wrolpi /etc/sudoers.d/90-wrolpi
chmod 0440 /etc/sudoers.d/90-wrolpi
# Verify this new file is valid.
visudo -c -f /etc/sudoers.d/90-wrolpi

# Install the systemd services
cp /opt/wrolpi/etc/raspberrypios/wrolpi*.service /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi.target /etc/systemd/system/
systemctl enable wrolpi-api.service
systemctl enable wrolpi-app.service
systemctl enable wrolpi-kiwix.service
systemctl enable wrolpi-help.service

# Copy config files necessary for map.
cp -r /opt/wrolpi/etc/raspberrypios/postgresql@15-map.service.d /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/renderd.conf /etc/renderd.conf
cp /opt/wrolpi/etc/raspberrypios/renderd.service /lib/systemd/system/renderd.service
# Configure Apache2 to listen on 8084.
cp /opt/wrolpi/etc/raspberrypios/ports.conf /etc/apache2/ports.conf
# Copy Leaflet files to Apache's directory so they can be used offline.
cp /opt/wrolpi/etc/raspberrypios/index.html \
  /opt/wrolpi/modules/map/leaflet.js \
  /opt/wrolpi/modules/map/leaflet.css /var/www/html/
chmod 644 /var/www/html/*
a2enmod ssl
a2enmod headers

systemctl enable renderd
/usr/bin/systemctl daemon-reload

# WROLPi needs a few privileged commands.
cp /opt/wrolpi/etc/raspberrypios/90-wrolpi /etc/sudoers.d/90-wrolpi
chmod 0440 /etc/sudoers.d/90-wrolpi
# Verify this new file is valid.
visudo -c -f /etc/sudoers.d/90-wrolpi

# Configure Postgresql.  Do this after the API is stopped.
/opt/wrolpi/scripts/initialize_api_db.sh
# wrolpi user is superuser so they can import maps.
sudo -iu postgres psql -c "alter user wrolpi with superuser"

# Configure renderd.
if [ ! -d /opt/openstreetmap-carto ]; then
  echo "/opt/openstreetmap-carto does not exist!  Has install completed?" && exit 1
fi

cp /opt/wrolpi/etc/raspberrypios/renderd.conf /etc/renderd.conf
# Enable mod_tile.
cp /opt/wrolpi/etc/raspberrypios/mod_tile.conf /etc/apache2/conf-available/mod_tile.conf

carto -v

# Initialize the map if it has not been initialized.
systemctl enable postgresql@15-map.service || :
systemctl start postgresql@15-map.service || :
sudo -iu postgres psql -c '\l' --port=5433 | grep -q gis || yes | /opt/wrolpi/scripts/initialize_map_db.sh
# Update openstreetmap-carto to use the new database.
grep -q 'port: 5433' /opt/openstreetmap-carto/project.mml || (
  # Append port line after dbname configuration line.
  sed -i '/dbname: "gis"/a \    port: 5433' /opt/openstreetmap-carto/project.mml
  (cd /opt/openstreetmap-carto/ && carto project.mml >mapnik.xml)
)
chown -R _renderd:_renderd /opt/openstreetmap-carto
# Disable JIT as recommended by mod_tile
sed -i 's/#jit =.*/jit = off/' /etc/postgresql/15/map/postgresql.conf

cp /opt/wrolpi/etc/raspberrypios/renderd.conf /etc/renderd.conf
# Configure Apache2 to listen on 8084.
cp /opt/wrolpi/etc/raspberrypios/ports.conf /etc/apache2/ports.conf
if [[ ${rpi} == true ]]; then
  cp /opt/wrolpi/etc/raspberrypios/000-default.conf /etc/apache2/sites-available/000-default.conf
else
  cp /opt/wrolpi/etc/debian12/000-default.conf /etc/apache2/sites-available/000-default.conf
fi

# Create the media directory.  This should be mounted by the maintainer.
[ -d /media/wrolpi ] || mkdir /media/wrolpi
# Create config directory if external drive is mounted, and is empty.
if grep -qs /media/wrolpi /proc/mounts && [ -z "$(ls -A /media/wrolpi)" ] && [ ! -d /media/wrolpi/config ]; then
  mkdir /media/wrolpi/config
fi

# Build the frontend app.
(cd /opt/wrolpi/app && npm run build)

# Change owner of the media directory, ignore any errors because the drive may be fat/exfat/etc.
chown wrolpi:wrolpi /media/wrolpi 2>/dev/null || echo "Ignoring failure to change media directory permissions."

chown -R wrolpi:wrolpi /home/wrolpi /opt/wrolpi*

# Copy MOTD once the repair has been successful.
cp /opt/wrolpi/etc/raspberrypios/motd/30-wrolpi.motd /etc/update-motd.d/30-wrolpi
chmod +x /etc/update-motd.d/*

systemctl restart renderd
systemctl restart wrolpi-help
systemctl start wrolpi.target

set +x

echo "Repair has completed.  You may run /opt/wrolpi/help.sh to check system status."
