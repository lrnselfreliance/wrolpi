#! /usr/bin/env bash
# This script will install WROLPi to `/opt/wrolpi` on a fresh/empty Raspberry Pi.  It is expected to be run once to
# install, and any subsequent runs will update WROLPi.  This script assumes it will be run as the `root` user.

set -x
set -e

# Installing git
apt update
apt install -y git raspberrypi-kernel-headers

# Getting the latest WROLPi code
git --version
git clone https://github.com/lrnselfreliance/wrolpi.git /opt/wrolpi ||
  cd /opt/wrolpi || exit 1

# Installing Python 3.7
python3 ||
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

# Installing python requirements files
shopt -s globstar nullglob
for file in /opt/wrolpi/**/requirements.txt; do
  pip install --upgrade -r "${file}"
done

# Any further pip commands will be global
deactivate

# Remove any old versions of docker
apt-get remove docker docker-engine docker.io containerd runc || : # ignore failures
# Installing docker repo and keys
[ -f /etc/apt/sources.list.d/wrolpi-docker.list ] || (
  # Docker repo not installed, install it
  apt install -y apt-transport-https ca-certificates curl gnupg-agent software-properties-common &&
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add - &&
    echo "deb [arch=armhf] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list
)
apt update
# Installing docker-ce & docker-compose
apt install -y docker-ce docker-ce-cli containerd.io
pip3 install docker-compose

# Installing docker-compose configs
[ -f /etc/systemd/system/wrolpi.service ] || (
  cp /opt/wrolpi/wrolpi.service /etc/systemd/system/
)

# Link to the entire wrolpi directory so docker-compose can find the Dockerfile(s)
if [ -d /etc/docker/compose ] && [ ! -L /etc/docker/compose/wrolpi ]; then
  ln -s /opt/wrolpi /etc/docker/compose/wrolpi
fi

# Building docker containers
docker-compose -f /etc/docker/compose/wrolpi/docker-compose.yml build --parallel

# Starting WROLPi
systemctl enable wrolpi.service
