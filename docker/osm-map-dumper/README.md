# OSM Map Dumper

A simple container which initializes planetary data, imports an Open Street Map PBF file, then dumps the Postgresql
database contents.  Contents are dumped to stdout using `pg_dump`, suitable for `pg_restore`.

Warning: Typically adds 2GB of planetary data.

## Usage

Import `map.osm.pbf`, dump to `output.dump`

`# docker run --rm -v /absolute/path/to/your/map.osm.pbf:/data/region.osm.pbf $(docker build -q .) > output.dump`

See: https://hub.docker.com/r/lrnselfreliance/osm-map-dumper
