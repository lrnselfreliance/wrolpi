# Pi-Gen
## Generate 64bit Raspberry Pi WROLPi image

1. Checkout pi-gen (64 bit):
   * `git clone --branch arm64 https://github.com/RPI-Distro/pi-gen.git`
2. Copy pi-gen config (modify for your directories):
   * `cp /home/user/wrolpi/pi-gen/config.txt /home/user/pi-gen/config.txt`
3. Copy stage scripts to pi-gen:
   * `cp -r /home/user/wrolpi/pi-gen/stage2/04-wrolpi /home/user/pi-gen/stage2/`
4. Change to the pi-gen directory:
   * `cd /home/user/pi-gen`
5. Create directory for files:
   * `mkdir stage2/04-wrolpi/files`
6. Convert a map PBF file to your initial map DB dump:
   * `docker run --rm -v /home/user/district-of-columbia-230111.osm.pbf:/data/region.osm.pbf lrnselfreliance/osm-map-dumper | gzip > /home/user/pi-gen/stage2/04-wrolpi/files/district-of-columbia-230111.dump.gz`
7. Run the build:
   * `sudo /bin/bash ./build.sh -c config.txt`

Your final image should be in `pi-gen/work/WROLPi/export-image/`
