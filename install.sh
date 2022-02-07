#! /usr/bin/env bash
# This script will install WROLPi to `/opt/wrolpi` on a fresh/empty Raspberry Pi.  It is expected to be run once to
# install, and any subsequent runs will update WROLPi.  This script assumes it will be run as the `root` user.

Help() {
  # Display Help
  echo "Install WROLPi onto this Raspberry Pi."
  echo
  echo "Syntax: install.sh [-h] [-b BRANCH]"
  echo "options:"
  echo "h     Print this help."
  echo "b     Install from this git BRANCH."
  echo
}

BRANCH="release"
while getopts ":hb:" option; do
  case $option in
  h) # display Help
    Help
    exit
    ;;
  b)
    BRANCH="${OPTARG}"
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

# Install yarn repos
curl -sL https://dl.yarnpkg.com/debian/pubkey.gpg | gpg --dearmor | sudo tee /usr/share/keyrings/yarnkey.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/yarnkey.gpg] https://dl.yarnpkg.com/debian stable main" |
  tee /etc/apt/sources.list.d/yarn.list
# Install npm repos.
curl -fsSL https://deb.nodesource.com/setup_14.x | bash -
# Update if we haven't updated in the last day.
[ -z "$(find -H /var/lib/apt/lists -maxdepth 0 -mtime -1)" ] && apt update
# Install dependencies
apt install -y git apt-transport-https ca-certificates curl gnupg-agent gcc libpq-dev software-properties-common \
  postgresql-12 nginx-full nginx-doc python3.8-minimal python3.8-dev python3.8-doc python3.8-venv \
  ffmpeg hostapd nodejs yarn texlive-latex-base texlive-latex-extra chromium-browser chromium-chromedriver

# Install Archiving tools.
npm install -g "gildas-lormeau/SingleFile#master"
npm install -g 'git+https://github.com/pirate/readability-extractor'

# Get the latest WROLPi code
git --version
git clone https://github.com/lrnselfreliance/wrolpi.git /opt/wrolpi || :
(cd /opt/wrolpi && git fetch && git checkout "${BRANCH}" && git reset --hard origin/"${BRANCH}") || exit 3

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
cd /opt/wrolpi/app
yarn --network-timeout 10000
yarn run build
yarn global add serve

# Install the WROLPi nginx config over the default nginx config.
cp /opt/wrolpi/nginx.conf /etc/nginx/nginx.conf
cp /opt/wrolpi/50x.html /var/www/50x.html
/usr/sbin/nginx -s reload

# Create the WROLPi user
grep wrolpi /etc/passwd || useradd -md /home/wrolpi wrolpi -s "$(command -v bash)"
chown -R wrolpi:wrolpi /opt/wrolpi

# Give WROLPi user a few privileged commands via sudo without password.
cat > /etc/sudoers.d/90-wrolpi << 'EOF'
%wrolpi ALL=(ALL) NOPASSWD:/usr/bin/nmcli,/usr/bin/cpufreq-set
EOF
# Verify this new file is valid.
visudo -c -f /etc/sudoers.d/90-wrolpi

# Create the media directory.  This should be mounted by the maintainer.
[ -d /media/wrolpi ] || mkdir /media/wrolpi
chown -R wrolpi:wrolpi /media/wrolpi

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
    sudo -u postgres createdb -O wrolpi wrolpi
)
# Init/upgrade the WROLPi database.
(cd /opt/wrolpi && /usr/bin/python3 /opt/wrolpi/main.py db upgrade)

# Configure the hotspot.
bash /opt/wrolpi/scripts/hotspot.sh

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
