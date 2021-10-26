#! /usr/bin/env bash
# This script will install WROLPi to `/opt/wrolpi` on a fresh/empty Raspberry Pi.  It is expected to be run once to
# install, and any subsequent runs will update WROLPi.  This script assumes it will be run as the `root` user.

Help() {
  # Display Help
  echo "Install WROLPi onto this Raspberry Pi."
  echo
  echo "Syntax: install.sh [-h]"
  echo "options:"
  echo "h     Print this help."
  echo
}

while getopts ":h" option; do
  case $option in
  h) # display Help
    Help
    exit
    ;;
  *) # invalid argument(s)
    echo "Error: Invalid option"
    exit 1
    ;;
  esac
done

set -x
set -e

# Check that WROLPi directory exists, and contains wrolpi.
[ -d /opt/wrolpi ] && [ ! -d /opt/wrolpi/wrolpi ] && echo "/opt/wrolpi exists but does not contain wrolpi!" && exit 2

# Update if we haven't updated in the last day.
[ -z "$(find -H /var/lib/apt/lists -maxdepth 0 -mtime -1)" ] && apt update
# Install dependencies
apt install -y git apt-transport-https ca-certificates curl gnupg-agent gcc libpq-dev npm software-properties-common \
  postgresql-12 nginx-full nginx-doc python3.8-full python3.8-dev python3.8-doc python3.8-venv \
  ffmpeg wkhtmltopdf

# Get the latest WROLPi code
git --version
git clone https://github.com/lrnselfreliance/wrolpi.git /opt/wrolpi ||
  (cd /opt/wrolpi && git pull) || exit 3

# Setup the virtual environment that main.py expects
pip3 --version || (
  # If no pip, install pip
  curl https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py &&
    python3 /tmp/get-pip.py
)
python3 -m venv /opt/wrolpi/venv
. /opt/wrolpi/venv/bin/activate

# Install python requirements files
pip3 install -r /opt/wrolpi/requirements.txt

# Build React app
[ ! -f /usr/local/bin/serve ] && npm -g install yarn serve
cd /opt/wrolpi/app
yarn --silent --network-timeout 10000
yarn run build
yarn global add serve

# Configure PostgreSQL
sudo -u postgres psql -c '\l' | grep wrolpi || (
  sudo -u postgres createuser wrolpi &&
    sudo -u postgres psql -c "alter user postgres password 'wrolpi'" &&
    sudo -u postgres psql -c "alter user wrolpi password 'wrolpi'" &&
    sudo -u postgres createdb -O wrolpi wrolpi
)
# Initialize the WROLPi database.
(cd /opt/wrolpi && /opt/wrolpi/venv/bin/python3 /opt/wrolpi/main.py db upgrade)

# Install the WROLPi nginx config over the default nginx config.
cp /opt/wrolpi/nginx.conf /etc/nginx/nginx.conf
/usr/sbin/nginx -s reload

# Create the WROLPi user
grep wrolpi /etc/passwd || useradd -d /opt/wrolpi wrolpi -s "$(which bash)"
chown -R wrolpi:wrolpi /opt/wrolpi

# Install the systemd services
cp /opt/wrolpi/wrolpi-api.service /etc/systemd/system/
cp /opt/wrolpi/wrolpi-app.service /etc/systemd/system/
cp /opt/wrolpi/wrolpi.target /etc/systemd/system/
/usr/bin/systemctl daemon-reload

set +x

ip=$(hostname -i | cut -d' ' -f1)

echo "WROLPi has successfully been installed!

Start the WROLPi services using:

sudo systemctl start wrolpi.target

then navigate to http://${ip}
"
