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
	postgresql-12 nginx-full nginx-doc python3.8-full python3.8-dev python3.8-doc python3.8-venv

# Get the latest WROLPi code
git --version
git clone https://github.com/lrnselfreliance/wrolpi.git /opt/wrolpi ||
  (cd /opt/wrolpi && git pull origin master) || exit 3

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

# Any further pip commands will be global
deactivate

# Build React app
cd /opt/wrolpi/app
npm -g install yarn serve
yarn --silent --network-timeout 10000
yarn run build
yarn global add serve

