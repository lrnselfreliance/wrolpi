# Pi-Gen

This directory exists to facilitate the creation of WROLPI Raspberry Pi OS images.
 
See https://github.com/RPI-Distro/pi-gen

## Generate 64bit Raspberry Pi WROLPi image

1. Convert a map PBF file to your initial map DB dump:
    * `docker run --rm -v /home/user/district-of-columbia-230111.osm.pbf:/data/region.osm.pbf lrnselfreliance/osm-map-dumper | gzip > pi-gen/stage2/04-wrolpi/files/gis-map.dump.gz`
2. Run the build.
   * `sudo ./build.sh`
3. The images are now in the `pi-gen` directory.
