# This file creates an OpenStreetMap container using the instructions here:
# https://switch2osm.org/manually-building-a-tile-server-18-04-lts/
FROM kartoza/postgis

RUN apt update
# Install tzdata with UTC to avoid being asked for our timezone
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y tzdata
# TODO could postgres be moved to a dedicated container?
# Install dependencies
RUN apt install -y apache2 apache2-dev autoconf build-essential bzip2 cmake curl fonts-noto-cjk fonts-noto-hinted \
  fonts-noto-unhinted g++ gdal-bin git-core libagg-dev libboost-all-dev libboost-dev libboost-filesystem-dev \
  libboost-system-dev libbz2-dev libcairo-dev libcairomm-1.0-dev libexpat1-dev libfreetype6-dev libgdal-dev \
  libgeos++-dev libgeos-dev libgeotiff-epsg libicu-dev liblua5.1-dev liblua5.2-dev libmapnik-dev libpq-dev libproj-dev \
  libprotobuf-c0-dev libtiff5-dev libtool libxml2-dev lua5.1 lua5.2 make mapnik-utils munin munin-node nodejs npm \
  protobuf-c-compiler python-mapnik sudo tar ttf-unifont unzip wget zlib1g-dev

# Configure the database
RUN sudo -iu postgres /usr/lib/postgresql/10/bin/postgres
RUN sudo -iu postgres createuser -s renderaccount
RUN sudo -iu postgres createdb -E UTF8 -O renderaccount gis
RUN sudo -iu postgres psql gis postgres -c 'CREATE EXTENSION postgis; CREATE EXTENSION hstore; ALTER TABLE ' \
  'geometry_columns OWNER TO renderaccount; ALTER TABLE spatial_ref_sys OWNER TO renderaccount;'

# Switch to a new user
RUN useradd -m renderaccount
RUN sudo su - renderaccount

# Install osm2pgsql
RUN git clone git://github.com/openstreetmap/osm2pgsql.git ~/osm2pgsql
RUN mkdir ~/osm2pgsql/build
RUN cd ~/osm2pgsql/build
RUN cmake ..
RUN make -j2
RUN make install

# Install mod_tile and renderd
RUN git clone -b switch2osm git://github.com/SomeoneElseOSM/mod_tile.git ~/switch2osm
RUN cd ~/switch2osm
RUN ./autogen.sh
RUN ./configure
RUN make -j2
RUN make install
RUN make install-mod_tile
RUN ldconfig

# Stylesheet configuration
RUN git clone git://github.com/gravitystorm/openstreetmap-carto.git ~/openstreetmap-carto
RUN cd ~/openstreetmap-carto
RUN npm install -g carto
RUN carto project.mml > mapnik.xml

# Load data
RUN sudo -u renderaccount -c mkdir ~/data
RUN sudo -u renderaccount osm2pgsql -d gis --create --slim  -G --hstore --tag-transform-script \
  ~/openstreetmap-carto/openstreetmap-carto.lua -C 2500 --number-processes 2 -S \
  ~/openstreetmap-carto/openstreetmap-carto.style /home/renderaccount/data/azerbaijan-latest.osm.pbf

# Shapefile download
RUN cd ~/openstreetmap-carto
RUN ./scripts/get-shapefiles.py
