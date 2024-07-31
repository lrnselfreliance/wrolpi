#!/usr/bin/env bash

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

set -x
set -e

# Install WROLPi Help repo.
git clone https://github.com/wrolpi/wrolpi-help.git /opt/wrolpi-help || :
git config --global --add safe.directory /opt/wrolpi-help
(cd /opt/wrolpi-help && git fetch && git checkout master && git reset --hard origin/master)
python3 -m venv /opt/wrolpi-help/venv
# Force re-install of mkdocs
/opt/wrolpi-help/venv/bin/pip3 uninstall -y mkdocs
/opt/wrolpi-help/venv/bin/pip3 install --upgrade -r /opt/wrolpi-help/requirements.txt

# Install the systemd service.
cp /opt/wrolpi/etc/raspberrypios/wrolpi-help.service /etc/systemd/system/
systemctl enable wrolpi-help.service
