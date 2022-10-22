#! /usr/bin/bash
# This script installs OpenStreetMap tile server.
# This server uses Apache2, renderd and mod_tile to render and display map tiles.

set -x
set -e

# Update if we haven't updated in the last day.
[ -z "$(find -H /var/lib/apt/lists -maxdepth 0 -mtime -1)" ] && apt update
# Install map dependencies.
apt install -y libboost-all-dev git tar unzip wget bzip2 build-essential autoconf libtool libxml2-dev libgeos-dev \
  libgeos++-dev libpq-dev libbz2-dev libproj-dev munin-node munin protobuf-c-compiler libfreetype6-dev libtiff5-dev \
  libicu-dev libgdal-dev libcairo2-dev libcairomm-1.0-dev libagg-dev liblua5.2-dev ttf-unifont lua5.1 liblua5.1-0-dev \
  postgis postgresql-12-postgis-3 postgresql-12-postgis-3-scripts osm2pgsql gdal-bin libmapnik-dev mapnik-utils \
  python3-mapnik apache2 apache2-dev libcurl4-gnutls-dev libiniparser-dev libmemcached-dev librados-dev \
  fonts-noto-cjk fonts-noto-hinted fonts-noto-unhinted postgresql-contrib

/usr/bin/npm install -g carto
/usr/bin/carto -v

function yes_or_no {
  while true; do
    read -p "$* [y/n]:" yn
    case $yn in
    [Yy]*) return 0 ;;
    [Nn]*) return 1 ;;
    esac
  done
}

sudo -u postgres psql -c '\l' | grep gis &&
  yes_or_no "Map database already exists.  Replace it?" &&
  systemctl stop renderd &&
  sudo -u postgres dropdb gis

# Create `gis` database for map.
sudo -u postgres psql -c '\l' | grep gis || sudo -u postgres createdb -E UTF8 -O wrolpi gis
sudo -u postgres psql -d gis -c "CREATE EXTENSION postgis;" || :
sudo -u postgres psql -d gis -c "CREATE EXTENSION hstore;" || :
sudo -u postgres psql -d gis -c "ALTER TABLE geometry_columns OWNER TO wrolpi;"
sudo -u postgres psql -d gis -c "ALTER TABLE spatial_ref_sys OWNER TO wrolpi;"

# Install Ubuntu 20.04 compatible mod_tile.
git clone -b switch2osm https://github.com/lrnselfreliance/mod_tile.git /tmp/mod_tile || :
if [ ! -f /usr/lib/apache2/modules/mod_tile.so ]; then
  (cd /tmp/mod_tile && ./autogen.sh && ./configure && make -j4 && make install && make install-mod_tile && ldconfig)
fi
# Install init/systemd config to start map service on startup.
cp /tmp/mod_tile/debian/renderd.init /etc/init.d/renderd
sudo chmod +x /etc/init.d/renderd
cp /tmp/mod_tile/debian/renderd.service /lib/systemd/system/
sed -ie 's/^RUNASUSER.*/RUNASUSER=wrolpi/' /etc/init.d/renderd
chmod +x /etc/init.d/renderd
[ ! -d /var/lib/mod_tile ] && mkdir /var/lib/mod_tile
chown wrolpi /var/lib/mod_tile

# Initialize gis database.
git clone https://github.com/lrnselfreliance/openstreetmap-carto.git /opt/openstreetmap-carto || :
chown -R wrolpi:wrolpi /opt/openstreetmap-carto
cd /opt/openstreetmap-carto
if [[ ! -f /opt/openstreetmap-carto/mapnik.xml || ! -s /opt/openstreetmap-carto/mapnik.xml ]]; then
  /usr/bin/carto project.mml >/opt/openstreetmap-carto/mapnik.xml
fi
# Use D.C. to initialized DB because it is so small.
wget --continue https://download.geofabrik.de/north-america/us/district-of-columbia-latest.osm.pbf \
  -O /tmp/district-of-columbia-latest.osm.pbf

# Initialize indexes and global polygons.   This may take multiple tries.
set +e
MAX_TRIES=3
COUNT=0
SUCCESS=false
external_data=false
dc_import=false
indexes=false
while [ "${COUNT}" -lt "${MAX_TRIES}" ]; do
  [[ "${external_data}" = false ]] &&
    sudo -u wrolpi /opt/openstreetmap-carto/scripts/get-external-data.py -d gis -U wrolpi &&
    external_data=true
  [[ "${dc_import}" = false ]] &&
    # Run import in "create" mode so basic tables will be created.
    sudo -u wrolpi nice -n 18 osm2pgsql -d gis --create --slim -G --hstore \
      --tag-transform-script /opt/openstreetmap-carto/openstreetmap-carto.lua \
      -C 2000 --number-processes 3 \
      -S /opt/openstreetmap-carto/openstreetmap-carto.style /tmp/district-of-columbia-latest.osm.pbf &&
    dc_import=true
  [[ "${indexes}" = false ]] &&
    sudo -u wrolpi psql -d gis -f /opt/openstreetmap-carto/indexes.sql &&
    indexes=true
  if [[ "${external_data}" == true && "${dc_import}" == true && "${indexes}" == true ]]; then
    SUCCESS=true
    break
  fi
  ((COUNT = COUNT + 1))
done

if [[ "${SUCCESS}" == false ]]; then
  echo "Could not import map data"
  exit 6
fi

set -e

cp /opt/wrolpi/etc/ubuntu20.04/renderd.conf /usr/local/etc/renderd.conf
# Enable mod_tile.
cp /opt/wrolpi/etc/ubuntu20.04/mod_tile.conf /etc/apache2/conf-available/mod_tile.conf

/usr/sbin/a2enconf mod_tile

# Configure Apache2 to listen on 8084.
cp /opt/wrolpi/etc/ubuntu20.04/ports.conf /etc/apache2/ports.conf
cp /opt/wrolpi/etc/ubuntu20.04/000-default.conf /etc/apache2/sites-available/000-default.conf
cp /opt/wrolpi/etc/ubuntu20.04/index.html /var/www/html/index.html
# Copy Leaflet files to Apache's directory so they can be used offline.
cp /opt/wrolpi/modules/map/leaflet.js /var/www/html/leaflet.js
cp /opt/wrolpi/modules/map/leaflet.css /var/www/html/leaflet.css

systemctl enable renderd
systemctl stop renderd
systemctl start renderd

systemctl stop apache2
systemctl start apache2
