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
  echo "Missing PBF file argument."
  exit 3
fi

if [ ! -f "${1}" ]; then
  echo "PBF file does not exist! ${1}"
  exit 4
fi

osm2pgsql -d gis --append --slim -G --hstore --tag-transform-script \
  /opt/openstreetmap-carto/openstreetmap-carto.lua -C 2000 --number-processes 4 \
  -S /opt/openstreetmap-carto/openstreetmap-carto.style "${1}"
