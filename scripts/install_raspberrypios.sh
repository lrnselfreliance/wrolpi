#!/usr/bin/env bash
echo "Raspberry Pi OS install start: $(date '+%Y-%m-%d %H:%M:%S')"

set -x
set -e

# Update if we haven't updated in the last day.
[ -z "$(find -H /var/lib/apt/lists -maxdepth 0 -mtime -1)" ] && apt update
# Install dependencies.
apt-get install -y \
  apt-transport-https \
  ca-certificates \
  calibre \
  chromium \
  chromium-driver \
  cpufrequtils \
  curl \
  ffmpeg \
  gcc \
  gnupg-agent \
  hostapd \
  htop \
  iotop \
  kiwix \
  kiwix-tools \
  libpq-dev \
  netcat \
  network-manager \
  nginx-doc \
  nginx-full \
  postgresql-13 \
  python3-dev \
  python3-doc \
  python3-full \
  python3-pip \
  python3-venv \
  software-properties-common \
  tmux \
  vim \
  zim-tools

# Install npm.
npm --version || curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt-get install -y nodejs
node -v
npm -v

# Install serve, and archiving tools.
sudo npm i -g serve@12.0.1 single-file-cli@1.0.33 readability-extractor@0.0.6

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

# Allow pi user to access database.
[ -d /home/pi ] && (
  cat >/home/pi/.pgpass <<'EOF'
127.0.0.1:5432:gis:_renderd:wrolpi
127.0.0.1:5432:wrolpi:wrolpi:wrolpi
EOF
  chown -R pi:pi /home/pi
  chmod 0600 /home/pi/.pgpass
)

# Give WROLPi group a few privileged commands via sudo without password.
cat >/etc/sudoers.d/90-wrolpi <<'EOF'
%wrolpi ALL=(ALL) NOPASSWD:/usr/bin/nmcli,/usr/bin/cpufreq-set
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl restart renderd.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl stop renderd.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl start renderd.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl restart wrolpi-kiwix.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl stop wrolpi-kiwix.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl start wrolpi-kiwix.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl restart wrolpi-api.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl stop wrolpi-api.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl start wrolpi-api.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl restart wrolpi-app.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl stop wrolpi-app.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl start wrolpi-app.service
%wrolpi ALL= NOPASSWD:/opt/wrolpi/scripts/import_map.sh
%wrolpi ALL= NOPASSWD:/usr/sbin/shutdown
EOF
chmod 660 /etc/sudoers.d/90-wrolpi
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
sudo -u postgres psql -c '\l' | grep wrolpi || (
  sudo -u postgres createuser -s wrolpi &&
    sudo -u postgres psql -c "alter user postgres password 'wrolpi'" &&
    sudo -u postgres psql -c "alter user wrolpi password 'wrolpi'" &&
    sudo -u postgres createdb -E UTF8 -O wrolpi wrolpi
)
# wrolpi user is superuser so they can import maps.
sudo -u postgres psql -c "alter user wrolpi with superuser"
# Initialize/upgrade the WROLPi database.
(cd /opt/wrolpi && /opt/wrolpi/venv/bin/python3 /opt/wrolpi/main.py db upgrade)

# Install map only if that script hasn't finished.
[ -f /var/www/html/leaflet.css ] || /opt/wrolpi/scripts/install_map_raspberrypios.sh

chown -R wrolpi:wrolpi /opt/wrolpi

set +x

ip=$(hostname -i | cut -d' ' -f1)
if [[ $ip == *":"* ]]; then
  # Don't suggest the ipv6 address.
  ip=$(hostname -i | cut -d' ' -f2)
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
