#! /usr/bin/env bash
# This script will install WROLPi to `/opt/wrolpi` on a fresh/empty Raspberry Pi.  It is expected to be run once to
# install, and any other run will update WROLPi.  This script assumes it will be run as the `root` user.

set -x
set -e

echo "Installing git"
apt update
apt install -y git

echo "Getting the latest WROLPi code"
git --version
git clone https://github.com/lrnselfreliance/wrolpi.git /opt/wrolpi || (cd /opt/wrolpi && git pull origin master)
cd /opt/wrolpi || exit 1

echo "Remove any old versions of docker"
# This command can fail
apt-get remove docker docker-engine docker.io containerd runc || :
echo "Installing docker repo and keys"
apt install -y apt-transport-https ca-certificates curl gnupg-agent software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
echo "deb [arch=armhf] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list
apt update
echo "Installing docker-ce & docker-compose"
apt install -y docker-ce docker-ce-cli containerd.io
curl -L "https://github.com/docker/compose/releases/download/1.24.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

echo "Installing Python 3.7"
apt install -y python3.7 python3.7-dev python3.7-doc python3.7-venv
# Setup the virtual environment that main.py expects
python3 -m venv /opt/wrolpi/venv
. /opt/wrolpi/venv/bin/activate

echo "Installing python requirements files"
shopt -s globstar nullglob
for file in /opt/wrolpi/**/requirements.txt
do
  pip install -r "${file}"
done

echo "Installing docker-compose configs"
cp -n /opt/wrolpi/docker-compose@.service /etc/systemd/system/ || :
mkdir -p /etc/docker/compose/wrolpi
dc_config="/etc/docker/compose/wrolpi/docker-compose.yml"
cp -f /opt/wrolpi/docker-compose.yml ${dc_config}

echo "Building docker containers"
docker-compose build -f ${dc_config} --parallel

echo "Starting WROLPi"
systemctl enable docker-compose@wrolpi
systemctl start docker-compose@wrolpi
