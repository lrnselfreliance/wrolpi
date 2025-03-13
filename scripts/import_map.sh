#!/usr/bin/env bash

MERGED_TMP_FILE=/tmp/wrolpi-merged.osm.pbf

if [ ! -f /opt/openstreetmap-carto/openstreetmap-carto.lua ]; then
  echo "openstreetmap-carto.lua file is missing.  Has install been completed?"
  exit 1
fi

if [ ! -f /opt/openstreetmap-carto/openstreetmap-carto.style ]; then
  echo "openstreetmap-carto.style file is missing.  Has install been completed?"
  exit 2
fi

if [ "${1}" == "" ]; then
  echo "Missing file argument."
  exit 3
fi

set -x

HAS_ICE_SHEET=false
sudo -iu postgres psql --port=5433 gis -c '\d' | grep icesheet_polygons && HAS_ICE_SHEET=true
if [ ${HAS_ICE_SHEET} = false ]; then
  echo "WROLPi: Missing icesheet_polygons.  Run reset_map.sh"
  exit 4
fi

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

function cleanup() {
  if [ -f ${MERGED_TMP_FILE} ]; then
    rm ${MERGED_TMP_FILE}
  fi
}

trap cleanup EXIT
cleanup

systemctl stop renderd

if [[ ${1} == *.osm.pbf ]]; then
  # Import PBF files.
  for i in "$@"; do
    if [[ $i != *.osm.pbf ]]; then
      echo "WROLPi: Cannot mix file types"
      exit 5
    fi
    if [ ! -f "${i}" ]; then
      echo "WROLPi: File does not exist! ${i}"
      exit 6
    fi
  done

  # Use 1/4 of the RAM to import.  1/2 causes crashes on RPi.
  RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
  MAX_CACHE=$((RAM_KB / 1024 / 4))

  pbf_path=${1}
  pbf_paths=($@)
  if [[ ${#pbf_paths[@]} -gt 1 ]]; then
    # More than one PBF, merge them before import.
    nice -n 18 osmium merge $@ -o ${MERGED_TMP_FILE}
    pbf_path=${MERGED_TMP_FILE}
  fi

  # Import as postgres user, then change ownership to _renderd.
  nice -n 18 sudo -iu postgres osm2pgsql -d gis --create --slim -G --hstore --port=5433 \
    --tag-transform-script /opt/openstreetmap-carto/openstreetmap-carto.lua \
    -C ${MAX_CACHE} \
    --number-processes 3 \
    -S /opt/openstreetmap-carto/openstreetmap-carto.style \
    "${pbf_path}"
  # Assign all data to _renderd so the map can be rendered.
  sudo -iu postgres psql --port=5433 -d gis -c 'ALTER TABLE external_data OWNER TO _renderd'
  sudo -iu postgres psql --port=5433 -d gis -c 'ALTER TABLE geography_columns OWNER TO _renderd'
  sudo -iu postgres psql --port=5433 -d gis -c 'ALTER TABLE geometry_columns OWNER TO _renderd'
  sudo -iu postgres psql --port=5433 -d gis -c "ALTER TABLE icesheet_outlines OWNER TO _renderd"
  sudo -iu postgres psql --port=5433 -d gis -c "ALTER TABLE icesheet_polygons OWNER TO _renderd"
  sudo -iu postgres psql --port=5433 -d gis -c "ALTER TABLE ne_100m_admin_0_boundary_lines_land OWNER TO _renderd"
  sudo -iu postgres psql --port=5433 -d gis -c "ALTER TABLE planet_osm_line OWNER TO _renderd"
  sudo -iu postgres psql --port=5433 -d gis -c "ALTER TABLE planet_osm_nodes OWNER TO _renderd"
  sudo -iu postgres psql --port=5433 -d gis -c "ALTER TABLE planet_osm_point OWNER TO _renderd"
  sudo -iu postgres psql --port=5433 -d gis -c "ALTER TABLE planet_osm_polygon OWNER TO _renderd"
  sudo -iu postgres psql --port=5433 -d gis -c "ALTER TABLE planet_osm_rels OWNER TO _renderd"
  sudo -iu postgres psql --port=5433 -d gis -c "ALTER TABLE planet_osm_roads OWNER TO _renderd"
  sudo -iu postgres psql --port=5433 -d gis -c "ALTER TABLE planet_osm_ways OWNER TO _renderd"
  sudo -iu postgres psql --port=5433 -d gis -c "ALTER TABLE simplified_water_polygons OWNER TO _renderd"
  sudo -iu postgres psql --port=5433 -d gis -c "ALTER TABLE spatial_ref_sys OWNER TO _renderd"
  sudo -iu postgres psql --port=5433 -d gis -c "ALTER TABLE water_polygons OWNER TO _renderd"
elif [[ ${1} == *.dump ]]; then
  if [ ! -f "${1}" ]; then
    echo "WROLPi: File does not exist! ${1}"
    exit 7
  fi
  # Import a Postgresql dump.
  nice -n 18 pg_restore --port=5433 -j3 --no-owner -d gis -U _renderd -h 127.0.0.1 "${1}"
else
  echo "WROLPi: Cannot import unknown file"
  exit 8
fi

# Clear map tile cache only after successful import.
yes | /bin/bash /opt/wrolpi/scripts/clear_map_cache.sh

# Use wget to fetch the first few layers of map tiles so the map is ready to use.
# Failure does not mean the import failed.
bash /opt/wrolpi/wrolpi/scripts/initialize_map_tiles.sh || :
