#! /usr/bin/env bash
# This script will install WROLPi to `/opt/wrolpi` on a fresh/empty Raspberry Pi.  It is expected to be run once to
# install, and any other run will update WROLPi.  This script assumes it will be run as the `root` user.

set -x

# Get the latest WROLPi code.
git clone https://github.com/lrnselfreliance/wrolpi.git /opt/wrolpi || (cd /opt/wrolpi && git pull origin master)
cd /opt/wrolpi || exit 1

# Remove any old versions of docker.
apt-get remove docker docker-engine docker.io containerd runc
# Install docker's dependencies
apt-get install apt-transport-https ca-certificates curl gnupg-agent software-properties-common
# Get docker's apt key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
# Add docker apt repo
add-apt-repository "deb [arch=arm64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
apt update
# Install docker -ce
apt install docker-ce docker-ce-cli containerd.io
# Get docker-compose
curl -L "https://github.com/docker/compose/releases/download/1.24.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Install Python 3.7
apt install python3.7 python3.7-dev python3.7-doc python3.7-venv
# Setup the virtual environment that main.py expects
python3 -m venv /opt/wrolpi/venv
. /opt/wrolpi/venv/bin/activate

# Install python requirements
shopt -s globstar nullglob
for req in /opt/wrolpi/**/requirements.txt
do
  pip install -r "${req}"
done

# Build docker containers
docker-compose build --parallel

# Start WROLPi
docker-compose up -d
