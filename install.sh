#! /usr/bin/env bash
# This script will install WROLPi to `/opt/wrolpi` on a fresh/empty Raspberry Pi.  It is expected to be run once to
# install, and any subsequent runs will update WROLPi.  This script assumes it will be run as the `root` user.

# Installation steps are roughly:
#  * Install git and kernel headers
#  * Clone WROLPi repo
#  * Install Python 3.7 or 3.5
#  * Setup virtual environment
#  * Install docker-ce and docker-compose
#  * Build docker containers
#  * Install and enable systemd configs

set -x
set -e

# Install git
apt update
apt install -y git raspberrypi-kernel-headers

# Get the latest WROLPi code
git --version
git clone https://github.com/lrnselfreliance/wrolpi.git /opt/wrolpi ||
  (cd /opt/wrolpi && git pull origin master) || exit 1

# Install Python 3.7 or 3.5
python3 --version ||
  apt install -y python3.7 python3.7-dev python3.7-doc python3.7-venv ||
  apt install -y python3.5 python3.5-dev python3.5-doc python3.5-venv

# Setup the virtual environment that main.py expects
pip3 --version || (
  # If no pip, install pip
  curl https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py &&
    python3 /tmp/get-pip.py
)
python3 -m venv /opt/wrolpi/venv
. /opt/wrolpi/venv/bin/activate

# Install python requirements files
pip3 install /opt/wrolpi/requirements.txt

# Any further pip commands will be global
deactivate

# Remove any old versions of docker
apt-get remove docker docker-engine docker.io containerd runc || : # ignore failures
# Installing docker repo and keys
[ -f /etc/apt/sources.list.d/wrolpi-docker.list ] || (
  # Docker repo not installed, install it.  Update the package list with these new repos.
  apt install -y apt-transport-https ca-certificates curl gnupg-agent software-properties-common &&
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add - &&
    echo "deb [arch=armhf] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list &&
    apt update
)
# Install docker-ce & docker-compose
apt install -y docker-ce docker-ce-cli containerd.io
pip3 install docker-compose

# Install docker-compose configs
cp -f /opt/wrolpi/wrolpi.service /etc/systemd/system/

# Build docker containers
docker-compose -f /opt/wrolpi/docker-compose.yml build --parallel

# Enable WROLPi on startup
systemctl enable wrolpi.service
