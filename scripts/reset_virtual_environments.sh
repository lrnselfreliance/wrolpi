#!/usr/bin/env bash
# Deletes and recreates all WROLPi Python virtual environments.
# This script requires internet access for pip install.

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

source /opt/wrolpi/wrolpi/scripts/lib.sh

yes_or_no "This script requires internet access. Do you want to continue?" || exit 0

set -e
set -x

echo "Stopping WROLPi services..."
systemctl stop wrolpi-api.service || :
systemctl stop wrolpi-controller.service || :
systemctl stop wrolpi-help.service || :

# Reset main API venv
echo "Resetting /opt/wrolpi/venv..."
rm -rf /opt/wrolpi/venv
python3 -m venv /opt/wrolpi/venv
/opt/wrolpi/venv/bin/pip3 install --upgrade pip
/opt/wrolpi/venv/bin/pip3 install -r /opt/wrolpi/requirements.txt

# Reset Controller venv
echo "Resetting /opt/wrolpi/controller/venv..."
rm -rf /opt/wrolpi/controller/venv
python3 -m venv /opt/wrolpi/controller/venv
/opt/wrolpi/controller/venv/bin/pip install --upgrade pip
/opt/wrolpi/controller/venv/bin/pip install -r /opt/wrolpi/controller/requirements.txt

# Reset Help venv
echo "Resetting /opt/wrolpi-help/venv..."
rm -rf /opt/wrolpi-help/venv
python3 -m venv /opt/wrolpi-help/venv
/opt/wrolpi-help/venv/bin/pip3 install --upgrade pip
/opt/wrolpi-help/venv/bin/pip3 install -r /opt/wrolpi-help/requirements.txt

# Fix ownership
chown -R wrolpi:wrolpi /opt/wrolpi /opt/wrolpi-help

echo "Restarting WROLPi services..."
systemctl start wrolpi-controller.service || :
systemctl start wrolpi-api.service || :
systemctl start wrolpi-help.service || :

echo "Virtual environments have been reset."
