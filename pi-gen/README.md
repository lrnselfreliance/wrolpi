# Pi-Gen

This directory exists to facilitate the creation of WROLPI Raspberry Pi OS images.

See https://github.com/RPI-Distro/pi-gen

## Generate 64bit Raspberry Pi WROLPi image

1. (Optional) Place any default map assets under `pi-gen/stage2/04-wrolpi/files/` if the image
   should ship with preloaded map data. Maps use PMTiles files served from `/media/wrolpi/map/`.

2. Run the build (or, with a specific git branch)

   * Build release branch (default)

         sudo ./build.sh

   * Build specific branch

         sudo ./build.sh -b master

3. The images are now in the `pi-gen` directory.
