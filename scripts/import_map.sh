#!/bin/bash

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

if [ ! -f "${1}" ]; then
  echo "File does not exist! ${1}"
  exit 4
fi

if [[ ${1} == *.osm.pbf ]]; then
  # Import a PBF file.
  nice -n 18 osm2pgsql -d gis --append --slim -G --hstore --tag-transform-script \
    /opt/openstreetmap-carto/openstreetmap-carto.lua -C 2000 --number-processes 3 \
    -S /opt/openstreetmap-carto/openstreetmap-carto.style "${1}"
elif [[ ${1} == *.dump ]]; then
  # Import a Postgresql dump.
  nice -n 18 pg_restore -j3 --no-owner -d gis "${1}"
else
  echo "Cannot import unknown map file"
  exit 5
fi
