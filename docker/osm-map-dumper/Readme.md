# OSM Map Dumper

A simple container which initializes planetary data, imports an Open Street Map PBF file, then dumps the Postgresql
database contents.  Contents are dumped using `pg_dump` __with__ compression.

`# docker run --rm -v /absolute/path/to/your/map.osm.pbf:/data/region.osm.pbf $(docker build -q .) > output.dump.gz`
