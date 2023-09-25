# Debian Live Config

## Generate Debian 12 ISO

This directory exists to facilitate the creation of WROLPi Debian images.

1. Convert a map PBF file to your initial map DB dump:
    * `docker run --rm -v /home/user/district-of-columbia-230111.osm.pbf:/data/region.osm.pbf lrnselfreliance/osm-map-dumper | gzip > debian-live-config/config/includes.chroot/opt/wrolpi-blobs/gis-map.dump.gz`
2. Run the build.
    * `sudo ./build.sh`
3. The ISO is now in the `debian-live-config` directory.
