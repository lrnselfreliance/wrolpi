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

HAS_ICE_SHEET=false
psql gis wrolpi -c '\d' | grep icesheet_polygons && HAS_ICE_SHEET=true
if [ ${HAS_ICE_SHEET} = false ]; then
  echo "WROLPi: Missing icesheet_polygons.  Run reset_map.sh"
  exit 4
fi

function cleanup() {
  if [ -f ${MERGED_TMP_FILE} ]; then
    rm ${MERGED_TMP_FILE}
  fi
}

trap cleanup EXIT
cleanup

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

  nice -n 18 osm2pgsql -d gis --create --slim -G --hstore -U _renderd -H 127.0.0.1 \
    --tag-transform-script /opt/openstreetmap-carto/openstreetmap-carto.lua \
    -C ${MAX_CACHE} \
    --number-processes 3 \
    -S /opt/openstreetmap-carto/openstreetmap-carto.style \
    "${pbf_path}"
elif [[ ${1} == *.dump ]]; then
  if [ ! -f "${1}" ]; then
    echo "WROLPi: File does not exist! ${1}"
    exit 7
  fi
  # Import a Postgresql dump.
  nice -n 18 pg_restore -j3 --no-owner -d gis -U _renderd -h 127.0.0.1 "${1}"
else
  echo "WROLPi: Cannot import unknown map file"
  exit 8
fi
