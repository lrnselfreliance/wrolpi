# Pi-Gen
## Generate 64bit Raspberry Pi WROLPi image

1. Checkout pi-gen (64 bit):
   * `git clone --branch arm64 https://github.com/RPI-Distro/pi-gen.git`
2. Copy these configs to pi-gen (modify for your directories):
   * `cp -r /home/user/wrolpi/pi-gen/stage3/02-wrolpi /home/user/pi-gen/stage3/`
3. Change to the pi-gen directory:
   * `cd /home/user/pi-gen`
4. Create directory for files:
   * `mkdir stage3/02-wrolpi/files`
5. Convert a map PBF file to your initial map DB dump:
   * `docker run --rm -v /home/user/district-of-columbia-230111.osm.pbf:/data/region.osm.pbf lrnselfreliance/osm-map-dumper | gzip > /home/user/pi-gen/stage3/02-wrolpi/files/district-of-columbia-230111.dump.gz`
6. Run the build:
   * `sudo /bin/bash ./build.sh -c config.txt`

Your final image should be in `pi-gen/work/WROLPi/export-image/`
