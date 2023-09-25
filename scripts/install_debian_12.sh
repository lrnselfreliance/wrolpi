#!/usr/bin/env bash
echo "Debian 12 install start: $(date '+%Y-%m-%d %H:%M:%S')"

set -x
set -e

# Update if we haven't updated in the last day.
[ -z "$(find -H /var/lib/apt/lists -maxdepth 0 -mtime -1)" ] && apt update
# Install dependencies.
apt-get install -y < /opt/wrolpi/debian-live-config/config/package-lists/wrolpi.list.chroot

# App dependencies were installed.
node -v
npm -v

# Install serve, and archiving tools.
single-file --version || sudo npm i -g serve@12.0.1 single-file-cli@1.0.33 readability-extractor@0.0.6 carto@1.2.0

# Build React app in background job.
cd /opt/wrolpi/app || exit 5
npm install || npm install || npm install || npm install # try install multiple times  :(
npm run build &

# Install python requirements in background job.
python3 -m venv /opt/wrolpi/venv
/opt/wrolpi/venv/bin/pip3 install -r /opt/wrolpi/requirements.txt &

wait $(jobs -p)

# Install the WROLPi nginx config over the default nginx config.
cp /opt/wrolpi/nginx.conf /etc/nginx/nginx.conf
cp /opt/wrolpi/50x.html /var/www/50x.html
/usr/sbin/nginx -s reload

# Create the WROLPi user
grep wrolpi: /etc/passwd || useradd -md /home/wrolpi wrolpi -s "$(command -v bash)"
cat >/home/wrolpi/.pgpass <<'EOF'
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

# Create the media directory.  This should be mounted by the maintainer.
[ -d /media/wrolpi ] || mkdir /media/wrolpi
chown wrolpi:wrolpi /media/wrolpi

# Install the systemd services
cp /opt/wrolpi/etc/raspberrypios/wrolpi-api.service /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi-app.service /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi-kiwix.service /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi.target /etc/systemd/system/
/usr/bin/systemctl daemon-reload
systemctl enable wrolpi-api.service
systemctl enable wrolpi-app.service
systemctl enable wrolpi-kiwix.service
# Stop the services so the user has to start them again.  We don't want to run outdated services when updating.
systemctl stop wrolpi-api.service
systemctl stop wrolpi-app.service
systemctl stop wrolpi-kiwix.service

# Configure Postgresql.  Do this after the API is stopped.
sudo -u postgres psql -c '\l' | grep wrolpi || yes | /opt/wrolpi/scripts/initialize_api_db.sh
# wrolpi user is superuser so they can import maps.
sudo -u postgres psql -c "alter user wrolpi with superuser"

# Install map only if that script hasn't finished.
[ -f /var/www/html/leaflet.css ] || /opt/wrolpi/scripts/install_map_debian_12.sh

chown -R wrolpi:wrolpi /opt/wrolpi

set +x

ip=$(hostname -I | cut -d' ' -f1)
if [[ $ip == *":"* ]]; then
  # Don't suggest the ipv6 address.
  ip=$(hostname -I | cut -d' ' -f2)
fi

echo "

WROLPi has successfully been installed!

Mount your external hard drive to /media/wrolpi if you have one.  Change the
file permissions if necessary:
 # sudo chown -R wrolpi:wrolpi /media/wrolpi

Start the WROLPi services using:
 # sudo systemctl start wrolpi.target

then navigate to:  http://${ip}

Or, join to the Wifi hotspot:
SSID: WROLPi
Password: wrolpi hotspot

When on the hotspot, WROLPi is accessible at http://192.168.0.1
"