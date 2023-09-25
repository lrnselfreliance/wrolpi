#!/usr/bin/env bash

source /opt/wrolpi/wrolpi/scripts/lib.sh

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

yes_or_no "Are you sure you want to delete map cache files?" || exit 0

set -x

# Clear map tile cache only after successful import.
[ -d /var/lib/mod_tile/ajt ] && rm -rf /var/lib/mod_tile/ajt && chown -R _renderd:_renderd /var/lib/mod_tile
[ -d /var/cache/renderd/tiles/ajt ] && rm -rf /var/cache/renderd/tiles/ajt && chown -R _renderd:_renderd /var/cache/renderd

# Restart renderd to forget the cache.
systemctl restart renderd
