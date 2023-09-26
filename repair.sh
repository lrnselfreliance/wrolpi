#!/usr/bin/env bash
# This script will attempt to repair a WROLPi installation.  It will not use internet.

cd /opt/wrolpi || (echo "Cannot repair.  /opt/wrolpi does not exist" && exit 1)

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
systemctl stop renderd || :
systemctl stop apache2 || :

# Reset any inadvertent changes to the WROLPi repo.
git reset HEAD --hard

# Rebuild the app after reset.
(cd app && npm run build)

# Copy configs to system.
cp /opt/wrolpi/nginx.conf /etc/nginx/nginx.conf
cp /opt/wrolpi/50x.html /var/www/50x.html
/usr/sbin/nginx -s reload

# Install the systemd services
cp /opt/wrolpi/etc/raspberrypios/wrolpi-api.service /etc/systemd/system/
if [[ ${rpi} == true ]]; then
  cp /opt/wrolpi/etc/raspberrypios/wrolpi-app.service /etc/systemd/system/
else
  cp /opt/wrolpi/etc/debian12/wrolpi-app.service /etc/systemd/system/
fi
cp /opt/wrolpi/etc/raspberrypios/wrolpi-kiwix.service /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi.target /etc/systemd/system/
/usr/bin/systemctl daemon-reload
systemctl enable wrolpi-api.service
systemctl enable wrolpi-app.service
systemctl enable wrolpi-kiwix.service

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
chown -R wrolpi:wrolpi /home/wrolpi /opt/wrolpi
chmod 0600 /home/wrolpi/.pgpass

# WROLPi needs a few privileged commands.
cp /opt/wrolpi/etc/raspberrypios/90-wrolpi /etc/sudoers.d/90-wrolpi
chmod 0440 /etc/sudoers.d/90-wrolpi
# Verify this new file is valid.
visudo -c -f /etc/sudoers.d/90-wrolpi

# Configure Postgresql.  Do this after the API is stopped.
sudo -u postgres psql -c '\l' | grep wrolpi || /opt/wrolpi/scripts/initialize_api_db.sh
# wrolpi user is superuser so they can import maps.
sudo -u postgres psql -c "alter user wrolpi with superuser"

# Install map only if that script hasn't finished.
/opt/wrolpi/scripts/install_map.sh

# Create the media directory.  This should be mounted by the maintainer.
[ -d /media/wrolpi ] || mkdir /media/wrolpi
chown wrolpi:wrolpi /media/wrolpi

chown -R wrolpi:wrolpi /opt/wrolpi*

systemctl start wrolpi.target
systemctl start apache2
systemctl start renderd

set +x

echo 'Waiting for services to start...'
sleep 10

# Run the help script to suggest what may not have been repaired.
/opt/wrolpi/help.sh
