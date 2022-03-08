#! /usr/bin/bash
# This script installs OpenStreetMap tile server.
# This server uses Apache2, renderd and mod_tile to render and display map tiles.

set -x
set -e

# Install map dependencies.
apt install -y libboost-all-dev git tar unzip wget bzip2 build-essential autoconf libtool libxml2-dev libgeos-dev \
  libgeos++-dev libpq-dev libbz2-dev libproj-dev munin-node munin protobuf-c-compiler libfreetype6-dev libtiff5-dev \
  libicu-dev libgdal-dev libcairo2-dev libcairomm-1.0-dev libagg-dev liblua5.2-dev ttf-unifont lua5.1 liblua5.1-0-dev \
  postgis postgresql-12-postgis-3 postgresql-12-postgis-3-scripts osm2pgsql gdal-bin libmapnik-dev mapnik-utils \
  python3-mapnik apache2 apache2-dev libcurl4-gnutls-dev libiniparser-dev libmemcached-dev librados-dev \
  fonts-noto-cjk fonts-noto-hinted fonts-noto-unhinted postgresql-contrib

/usr/bin/npm install -g carto
/usr/bin/carto -v

# Create `gis` database for map.
sudo -u postgres psql -c '\l' | grep gis || sudo -u postgres createdb -E UTF8 -O wrolpi gis
sudo -u postgres psql -d gis -c "CREATE EXTENSION postgis;" || :
sudo -u postgres psql -d gis -c "CREATE EXTENSION hstore;" || :
sudo -u postgres psql -d gis -c "ALTER TABLE geometry_columns OWNER TO wrolpi;"
sudo -u postgres psql -d gis -c "ALTER TABLE spatial_ref_sys OWNER TO wrolpi;"

# Install Ubuntu 20.04 compatible mod_tile.
git clone -b switch2osm git://github.com/lrnselfreliance/mod_tile.git /tmp/mod_tile || :
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
git clone git://github.com/lrnselfreliance/openstreetmap-carto.git /opt/openstreetmap-carto || :
chown -R wrolpi:wrolpi /opt/openstreetmap-carto
cd /opt/openstreetmap-carto
if [[ ! -f /opt/openstreetmap-carto/mapnik.xml || ! -s /opt/openstreetmap-carto/mapnik.xml ]]; then
  /usr/bin/carto project.mml >/opt/openstreetmap-carto/mapnik.xml
fi
# Use D.C. to initialized DB because it is so small.
wget --continue https://download.geofabrik.de/north-america/us/district-of-columbia-latest.osm.pbf \
  -O /tmp/district-of-columbia-latest.osm.pbf
sudo -u wrolpi /usr/bin/osm2pgsql -d gis --create --slim -G --hstore --tag-transform-script \
  /opt/openstreetmap-carto/openstreetmap-carto.lua -C 2000 --number-processes 4 \
  -S /opt/openstreetmap-carto/openstreetmap-carto.style /tmp/district-of-columbia-latest.osm.pbf
# Initialize indexes and global polygons.
sudo -u wrolpi psql -d gis -f /opt/openstreetmap-carto/indexes.sql
sudo -u wrolpi /opt/openstreetmap-carto/scripts/get-external-data.py -d gis -U wrolpi

cat >/usr/local/etc/renderd.conf <<'EOF'
[renderd]
num_threads=4
tile_dir=/var/lib/mod_tile
stats_file=/var/run/renderd/renderd.stats

[mapnik]
plugins_dir=/usr/lib/mapnik/3.0/input
font_dir=/usr/share/fonts/truetype
font_dir_recurse=1

[ajt]
URI=/hot/
TILEDIR=/var/lib/mod_tile
XML=/opt/openstreetmap-carto/mapnik.xml
HOST=localhost
TILESIZE=256
MAXZOOM=20
EOF

# Enable mod_tile.
cat >>/etc/apache2/conf-available/mod_tile.conf <<'EOF'
LoadModule tile_module /usr/lib/apache2/modules/mod_tile.so
EOF
/usr/sbin/a2enconf mod_tile

# Configure Apache2 to listen on 8084.
cat >/etc/apache2/ports.conf <<'EOF'
# If you just change the port or add more ports here, you will likely also
# have to change the VirtualHost statement in
# /etc/apache2/sites-enabled/000-default.conf

Listen 8084

<IfModule ssl_module>
	Listen 443
</IfModule>

<IfModule mod_gnutls.c>
	Listen 443
</IfModule>

# vim: syntax=apache ts=4 sw=4 sts=4 sr noet
EOF

cat >/etc/apache2/sites-available/000-default.conf <<'EOF'
<VirtualHost *:8084>
	# The ServerName directive sets the request scheme, hostname and port that
	# the server uses to identify itself. This is used when creating
	# redirection URLs. In the context of virtual hosts, the ServerName
	# specifies what hostname must appear in the request's Host: header to
	# match this virtual host. For the default virtual host (this file) this
	# value is not decisive as it is used as a last resort host regardless.
	# However, you must set it for any further virtual host explicitly.
	#ServerName www.example.com

	ServerAdmin webmaster@localhost

	LoadTileConfigFile /usr/local/etc/renderd.conf
	ModTileRenderdSocketName /var/run/renderd/renderd.sock
	# Timeout before giving up for a tile to be rendered
	ModTileRequestTimeout 0
	# Timeout before giving up for a tile to be rendered that is otherwise missing
	ModTileMissingRequestTimeout 30

	DocumentRoot /var/www/html

	# Available loglevels: trace8, ..., trace1, debug, info, notice, warn,
	# error, crit, alert, emerg.
	# It is also possible to configure the loglevel for particular
	# modules, e.g.
	#LogLevel info ssl:warn

	ErrorLog ${APACHE_LOG_DIR}/error.log
	CustomLog ${APACHE_LOG_DIR}/access.log combined

	# For most configuration files from conf-available/, which are
	# enabled or disabled at a global level, it is possible to
	# include a line for only one particular virtual host. For example the
	# following line enables the CGI configuration for this host only
	# after it has been globally disabled with "a2disconf".
	#Include conf-available/serve-cgi-bin.conf
</VirtualHost>

# vim: syntax=apache ts=4 sw=4 sts=4 sr noet
EOF

cat >/var/www/html/index.html <<'EOF'
<!DOCTYPE HTML>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="/leaflet.js"></script>
    <link rel="stylesheet" href="/leaflet.css" />
    <style>
      html, body {
        height: 100%;
        padding: 0;
        margin: 0;
      }
      #map {
        /* configure the size of the map */
        width: 100%;
        height: 100%;
      }
    </style>
  </head>
  <body>
    <div id="map"></div>
    <script>
      // initialize Leaflet
      var map = L.map('map').setView({lon: 0, lat: 0}, 2);

      // add the OpenStreetMap tiles
      L.tileLayer(`http://${window.location.hostname}:8084/hot/{z}/{x}/{y}.png`, {
        maxZoom: 19,
        attribution: '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap contributors</a>'
      }).addTo(map);

      // show the scale bar on the lower left corner
      L.control.scale({imperial: true, metric: true}).addTo(map);
    </script>
  </body>
</html>
EOF

# Copy Leaflet files to Apache's directory so they can be used offline.
cp /opt/wrolpi/modules/map/leaflet.js /var/www/html/leaflet.js
cp /opt/wrolpi/modules/map/leaflet.css /var/www/html/leaflet.css

systemctl enable renderd
systemctl stop renderd
systemctl start renderd

systemctl stop apache2
systemctl start apache2
