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
(cd /opt/wrolpi-help && git fetch && git checkout master && git reset --hard origin/master)
python3 -m venv /opt/wrolpi-help/venv
/opt/wrolpi-help/venv/bin/pip3 install -r /opt/wrolpi-help/requirements.txt

# Install the systemd service.
cp /opt/wrolpi/etc/raspberrypios/wrolpi-help.service /etc/systemd/system/
systemctl enable wrolpi-help.service
