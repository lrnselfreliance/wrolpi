#!/usr/bin/env bash
echo "Debian 12 install start: $(date '+%Y-%m-%d %H:%M:%S')"

set -x
set -e

# Update if we haven't updated in the last day.
[ -z "$(find -H /var/lib/apt/lists -maxdepth 0 -mtime -1)" ] && apt update
# Install dependencies.
apt-get install -y $(cat /opt/wrolpi/debian-live-config/config/package-lists/wrolpi.list.chroot)

# App dependencies were installed.
node -v
npm -v

# Install serve, and archiving tools.
single-file --version || sudo npm i -g serve@12.0.1 single-file-cli@1.0.33 readability-extractor@0.0.6 carto@1.2.0

# Build React app in background job.
cd /opt/wrolpi/app || exit 5
npm install || npm install || npm install || npm install # try install multiple times  :(

# Install python requirements in background job.
python3 -m venv /opt/wrolpi/venv
/opt/wrolpi/venv/bin/pip3 install -r /opt/wrolpi/requirements.txt

# Create the WROLPi user
grep wrolpi: /etc/passwd || useradd -md /home/wrolpi wrolpi -s "$(command -v bash)"

# Get map dependencies.
[ -d /opt/openstreetmap-carto ] && chown -R wrolpi:wrolpi /opt/openstreetmap-carto
git clone https://github.com/lrnselfreliance/openstreetmap-carto.git /opt/openstreetmap-carto || :
(cd /opt/openstreetmap-carto && git fetch && git checkout master && git reset --hard origin/master && git pull --ff)
chown -R _renderd:_renderd /opt/openstreetmap-carto

# Get map initialization dump.
if [[ ! -f /opt/wrolpi-blobs/gis-map.dump.gz || ! -s /opt/wrolpi-blobs/gis-map.dump.gz ]]; then
  wget https://wrolpi.nyc3.cdn.digitaloceanspaces.com/gis-map.dump.gz -O /opt/wrolpi-blobs/gis-map.dump.gz
fi

# Repair will install configs and restart services.
/opt/wrolpi/repair.sh

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
