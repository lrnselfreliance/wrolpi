#!/usr/bin/env bash
# This script will attempt to repair a WROLPi installation.  It will not use internet.

cd /opt/wrolpi || (echo "Cannot repair.  /opt/wrolpi does not exist" && exit 1)

rpi=false
debian12=false
if (grep 'Raspberry Pi' /proc/cpuinfo >/dev/null); then
  rpi=true
fi
if (grep 'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"' /etc/os-release >/dev/null); then
  debian12=true
fi

set -e
set -x

# Stop services if they are running.
systemctl stop wrolpi-api.service || :
systemctl stop wrolpi-app.service || :
systemctl stop wrolpi-kiwix.service || :

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
[ -f /var/www/html/leaflet.css ] || /opt/wrolpi/scripts/install_map_debian_12.sh

# Create the media directory.  This should be mounted by the maintainer.
[ -d /media/wrolpi ] || mkdir /media/wrolpi
chown wrolpi:wrolpi /media/wrolpi

chown -R wrolpi:wrolpi /opt/wrolpi*

systemctl start wrolpi.target

# Run the help script to suggest what may not have been repaired.
/opt/wrolpi/help.sh
