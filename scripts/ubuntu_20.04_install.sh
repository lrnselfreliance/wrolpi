#!/bin/bash

set -x
set -e

# Install npm repos.
curl -fsSL https://deb.nodesource.com/setup_14.x | bash -
# Update if we haven't updated in the last day.
[ -z "$(find -H /var/lib/apt/lists -maxdepth 0 -mtime -1)" ] && apt update
# Install dependencies
apt install -y apt-transport-https ca-certificates curl gnupg-agent gcc libpq-dev software-properties-common \
  postgresql-12 nginx-full nginx-doc python3.8-minimal python3.8-dev python3.8-doc python3.8-venv \
  ffmpeg hostapd nodejs texlive-latex-base texlive-latex-extra chromium-browser chromium-chromedriver \
  cpufrequtils network-manager

# Install Archiving tools.
npm install -g "gildas-lormeau/SingleFile#master"
npm install -g 'git+https://github.com/pirate/readability-extractor'

# Setup the virtual environment that main.py expects
pip3 --version || (
  # If no pip, install pip
  curl https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py &&
    python3 /tmp/get-pip.py
)

# Install python requirements files
pip3 install -r /opt/wrolpi/requirements.txt

# Build React app
[ ! -f /usr/local/bin/serve ] && npm -g install serve
cd /opt/wrolpi/app || exit 5
npm install || npm install || npm install || npm install # try install multiple times
npm run build

# Install the WROLPi nginx config over the default nginx config.
cp /opt/wrolpi/nginx.conf /etc/nginx/nginx.conf
cp /opt/wrolpi/50x.html /var/www/50x.html
/usr/sbin/nginx -s reload

# Create the WROLPi user
grep wrolpi /etc/passwd || useradd -md /home/wrolpi wrolpi -s "$(command -v bash)"
chown -R wrolpi:wrolpi /opt/wrolpi

# Give WROLPi group a few privileged commands via sudo without password.
cat >/etc/sudoers.d/90-wrolpi <<'EOF'
%wrolpi ALL=(ALL) NOPASSWD:/usr/bin/nmcli,/usr/bin/cpufreq-set
EOF
chmod 660 /etc/sudoers.d/90-wrolpi
# Verify this new file is valid.
visudo -c -f /etc/sudoers.d/90-wrolpi

# Create the media directory.  This should be mounted by the maintainer.
[ -d /media/wrolpi ] || mkdir /media/wrolpi
chown wrolpi:wrolpi /media/wrolpi

# Install the systemd services
cp /opt/wrolpi/systemd/wrolpi-api.service /etc/systemd/system/
cp /opt/wrolpi/systemd/wrolpi-app.service /etc/systemd/system/
cp /opt/wrolpi/systemd/wrolpi.target /etc/systemd/system/
/usr/bin/systemctl daemon-reload
systemctl enable wrolpi-api.service
systemctl enable wrolpi-app.service
# Stop the services so the user has to start them again.  We don't want to run outdated services when updating.
systemctl stop wrolpi-api.service
systemctl stop wrolpi-app.service

# Configure Postgresql.  Do this after the API is stopped.
sudo -u postgres psql -c '\l' | grep wrolpi || (
  sudo -u postgres createuser wrolpi &&
    sudo -u postgres psql -c "alter user postgres password 'wrolpi'" &&
    sudo -u postgres psql -c "alter user wrolpi password 'wrolpi'" &&
    sudo -u postgres createdb -E UTF8 -O wrolpi wrolpi
)
# Initialize/upgrade the WROLPi database.
(cd /opt/wrolpi && /usr/bin/python3 /opt/wrolpi/main.py db upgrade)

# Run the map installation script.
/opt/wrolpi/scripts/ubuntu_20.04_install_map.sh

set +x

ip=$(hostname -i | cut -d' ' -f1)
if [[ $ip == *":"* ]]; then
  # Don't suggest the ipv6 address.
  ip=$(hostname -i | cut -d' ' -f2)
fi

echo "

WROLPi has successfully been installed!

Mount your external hard drive to /media/wrolpi if you have one.

Start the WROLPi services using:
 # sudo systemctl start wrolpi.target

then navigate to:  http://${ip}

Or, join to the Wifi hotspot:
SSID: WROLPi
Password: wrolpi hotspot

When on the hotspot, WROLPi is accessible at http://192.168.0.1
"
