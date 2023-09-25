#! /usr/bin/env bash
# Installs any new dependencies of the App and API.  Uses internet.

set -e
set -x

# Install any App dependencies.
cd /opt/wrolpi/app || exit 1
npm install || npm install || npm install || npm install # try install multiple times  :(

# Install any new Python requirements.
/opt/wrolpi/venv/bin/pip3 install -r /opt/wrolpi/requirements.txt
# Upgrade the WROLPi database.
(cd /opt/wrolpi && /opt/wrolpi/venv/bin/python3 /opt/wrolpi/main.py db upgrade)

# Install any configs, restart services.
/opt/wrolpi/repair.sh
