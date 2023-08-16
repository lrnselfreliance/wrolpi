#!/usr/bin/env bash
# Simple script which removes the Renderd map tile cache files.

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

[ -d /var/lib/mod_tile/ajt ] && rm -rf /var/lib/mod_tile/ajt
[ -d /var/cache/renderd/tiles/ajt ] && rm -rf /var/cache/renderd/tiles/ajt

systemctl restart renderd
