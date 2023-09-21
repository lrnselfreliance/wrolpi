#!/usr/bin/env bash

source /opt/wrolpi/wrolpi/scripts/lib.sh

yes_or_no "Are you sure you want to delete map cache files?" || exit 0

# Clear map tile cache only after successful import.
[ -d /var/lib/mod_tile/ajt ] && rm -rf /var/lib/mod_tile/ajt
[ -d /var/cache/renderd/tiles/ajt ] && rm -rf /var/cache/renderd/tiles/ajt
