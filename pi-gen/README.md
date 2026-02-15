# Pi-Gen

This directory exists to facilitate the creation of WROLPI Raspberry Pi OS images.

See https://github.com/RPI-Distro/pi-gen

## Generate 64bit Raspberry Pi WROLPi image

1. Convert a map PBF file to your initial map DB dump:

       docker run --rm -v /home/user/district-of-columbia-230111.osm.pbf:/data/region.osm.pbf lrnselfreliance/osm-map-dumper > pi-gen/stage2/04-wrolpi/files/map-db-gis.dump

   The output is already compressed (PostgreSQL custom format with `--compress 9`).

   Verify the dump format is correct:

       file pi-gen/stage2/04-wrolpi/files/map-db-gis.dump
       # Should show: "PostgreSQL custom database dump"

2. Run the build (or, with a specific git branch)

   * Build master branch

         sudo ./build.sh

   * Build specific branch

         sudo ./build.sh -b release-candidate

3. The images are now in the `pi-gen` directory.
