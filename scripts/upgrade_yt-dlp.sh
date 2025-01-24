#! /usr/bin/env bash

set -e

# Re-execute this script if it wasn't called with sudo.
if [ "$(whoami)" != "wrolpi" ]; then
    sudo -u wrolpi "$0" "$@"
    exit $?
fi

. /opt/wrolpi/venv/bin/activate
if pip install --upgrade yt-dlp | grep -q "Successfully installed"; then
  echo "yt-dlp was upgraded."
  echo "You must restart the API:"
  echo "   sudo systemctl restart wrolpi-api"
  exit 0
else
  echo "yt-dlp is already up to date"
  exit 1
fi
