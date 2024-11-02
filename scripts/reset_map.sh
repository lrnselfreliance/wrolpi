#!/usr/bin/env bash

source /opt/wrolpi/wrolpi/scripts/lib.sh

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

# Change directory to avoid "sudo" home directory warning.
cd /tmp

if sudo -u postgres psql -l 2>/dev/null | grep gis >/dev/null; then
  yes_or_no "Are you sure you want to delete the map database and cache?  This can't be undone!" || exit 0
fi

function cleanup() {
  sudo rm -f /tmp/tile.png /tmp/tile.md5
}

trap cleanup EXIT
cleanup

set -e
set -x

systemctl stop renderd

sudo -u postgres dropdb gis || :
sudo -u postgres dropuser _renderd || :

# Reset "imported" status of any map files.
sudo -u postgres psql -d wrolpi -c "UPDATE map_file SET imported=false"

yes | /opt/wrolpi/scripts/initialize_map_db.sh

# Use curl to fetch the first few layers of map tiles so the map is ready to use.
bash /opt/wrolpi/wrolpi/scripts/initialize_map_tiles.sh

# Check the hash value of a Washington DC tile from /opt/wrolpi-blobs/gis-map.dump.gz
wget "https://127.0.0.1:8084/hot/13/2345/3134.png" \
  --quiet \
  --no-check-certificate \
  --timeout 600 \
  -O /tmp/tile.png
set +x
echo "b9b7884d64b555fd4f433f991a86cc72  /tmp/tile.png" > /tmp/tile.md5
if md5sum -c /tmp/tile.md5 >/dev/null ; then
  echo "Map tile was rendered correctly"
else
  echo "Map tile was not rendered correctly!"
  exit 1
fi

echo "Map has been reset."
