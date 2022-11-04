#!/bin/bash

# Use 1/4 of the RAM to import.  1/2 causes crashes on RPi.
RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MAX_CACHE=$((RAM_KB / 1024 / 4))

function yes_or_no {
  while true; do
    read -p "$* [y/n]:" yn
    case $yn in
    [Yy]*) return 0 ;;
    [Nn]*) return 1 ;;
    esac
  done
}

Help() {
  # Display Help
  echo "Reset the Map cache/database"
  echo
  echo "Syntax: reset_map.sh [-h] [-f]"
  echo "options:"
  echo "h     Print this help."
  echo "f     Reset without prompt."
  echo
}

FORCE=false
while getopts ":hf:" option; do
  case $option in
  h) # display Help
    Help
    exit
    ;;
  f)
    FORCE=true
    ;;
  *) # invalid argument(s)
    echo "Error: Invalid option"
    exit 1
    ;;
  esac
done

if [ "${FORCE}" == false ]; then
  yes_or_no "Are you sure you want to delete the map database and cache?  This can't be undone!" || exit 1
fi

if [[ ! -f /usr/lib/apache2/modules/mod_tile.so ||
  ! -f /opt/openstreetmap-carto/mapnik.xml ||
  ! -s /opt/openstreetmap-carto/mapnik.xml ||
  ! -f /opt/openstreetmap-carto/scripts/get-external-data.py ||
  ! -f /opt/openstreetmap-carto/openstreetmap-carto.style ||
  ! -f /opt/openstreetmap-carto/indexes.sql ]]; then
  echo "The map has not been installed.  Run install.sh"
  exit 2
fi

set -e
set -x

systemctl stop renderd

if [ -d /var/lib/mod_tile ]; then
  rm -rf /var/lib/mod_tile/*
else
  mkdir /var/lib/mod_tile
fi
chown -R wrolpi:wrolpi /var/lib/mod_tile

sudo -u postgres dropdb gis || :

sudo -u postgres createdb -E UTF8 -O wrolpi gis
sudo -u postgres psql -d gis -c "CREATE EXTENSION postgis;" || :
sudo -u postgres psql -d gis -c "CREATE EXTENSION hstore;" || :
sudo -u postgres psql -d gis -c "ALTER TABLE geometry_columns OWNER TO wrolpi;"
sudo -u postgres psql -d gis -c "ALTER TABLE spatial_ref_sys OWNER TO wrolpi;"

# Reset "imported" status of any map files.
sudo -u postgres psql -d wrolpi -c "UPDATE map_file SET imported=false"

/opt/wrolpi/scripts/initialize_map.sh

echo "Map has been reset"
