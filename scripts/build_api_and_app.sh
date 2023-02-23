#! /usr/bin/env bash
# This script will rebuild and install dependencies of the API and App.

set -x
set -e

# Install any App dependencies.
cd /opt/wrolpi/app || exit 1
npm install || npm install || npm install || npm install # try install multiple times  :(
# Build app in the background.
npm run build &

# Install python requirements in background job.
/opt/wrolpi/venv/bin/pip3 install -r /opt/wrolpi/requirements.txt &

wait $(jobs -p)

# Upgrade the WROLPi database.
(cd /opt/wrolpi && /opt/wrolpi/venv/bin/python3 /opt/wrolpi/main.py db upgrade)

systemctl start wrolpi.target
