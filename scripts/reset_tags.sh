#!/usr/bin/env bash

source /opt/wrolpi/wrolpi/scripts/lib.sh

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

yes_or_no "Are you sure you want to delete all tags? This cannot be undone." || exit 0

set -x

systemctl stop wrolpi-api

# Delete all tag relationships and tags from the database.
sudo -iu postgres psql -d wrolpi -c "DELETE FROM tag_zim;"
sudo -iu postgres psql -d wrolpi -c "DELETE FROM tag_file;"
sudo -iu postgres psql -d wrolpi -c "DELETE FROM tag;"

systemctl start wrolpi-api