#!/bin/bash
# https://github.com/RPI-Distro/pi-gen

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
BUILD_DIR=/var/tmp/wrolpi-build-pi-gen

VERSION=$(cat "${SCRIPT_DIR}/../wrolpi/version.txt")

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

if [ ! -f "${SCRIPT_DIR}/stage2/04-wrolpi/files/map-db-gis.dump" ]; then
  echo "stage2/04-wrolpi/files/map-db-gis.dump does not exist!"
  exit 1
fi

# Validate dump file format - must be PostgreSQL custom format (PGDMP magic)
DUMP_FILE="${SCRIPT_DIR}/stage2/04-wrolpi/files/map-db-gis.dump"
DUMP_HEADER=$(head -c 5 "${DUMP_FILE}" 2>/dev/null | od -An -tx1 | tr -d ' \n')

if [[ "${DUMP_HEADER:0:6}" == "504744" ]]; then
  echo "map-db-gis.dump: Valid PostgreSQL custom format"
elif [[ "${DUMP_HEADER:0:6}" == "1f8b08" ]]; then
  # Check if gzipped content is custom format
  INNER_HEADER=$(gunzip -c "${DUMP_FILE}" 2>/dev/null | head -c 5 | od -An -tx1 | tr -d ' \n')
  if [[ "${INNER_HEADER:0:6}" == "504744" ]]; then
    echo "map-db-gis.dump: Valid gzipped PostgreSQL custom format"
  else
    echo "ERROR: map-db-gis.dump is gzipped but does NOT contain PostgreSQL custom format!"
    echo "Inner header: ${INNER_HEADER} (expected to start with 504744 for 'PGDMP')"
    echo "The dump was likely created incorrectly. Use:"
    echo "  docker run --rm -v /path/to/file.osm.pbf:/data/region.osm.pbf lrnselfreliance/osm-map-dumper > map-db-gis.dump"
    exit 1
  fi
else
  echo "ERROR: map-db-gis.dump has invalid format!"
  echo "Header: ${DUMP_HEADER} (expected to start with 504744 for 'PGDMP' or 1f8b08 for gzip)"
  echo "Create the dump using:"
  echo "  docker run --rm -v /path/to/file.osm.pbf:/data/region.osm.pbf lrnselfreliance/osm-map-dumper > map-db-gis.dump"
  exit 1
fi

CHROOTFS="${BUILD_DIR}/work/WROLPi/stage0/rootfs"

cleanup() {
    [ -f /var/tmp/bookworm-arm64.zip ] && rm /var/tmp/bookworm-arm64.zip

    # Only unmount if it is actually a mountpoint
    for mp in \
        "${CHROOTFS}/dev/pts" \
        "${CHROOTFS}/sys" \
        "${CHROOTFS}/proc" \
        "${CHROOTFS}/run" \
        "${CHROOTFS}/tmp" \
        "${CHROOTFS}/dev"; do

        if mountpoint -q "${mp}" 2>/dev/null; then
            umount "${mp}" 2>/dev/null || umount -l "${mp}" 2>/dev/null
        fi
    done

    # Final safety net – remove the whole build tree
    rm -rf "${BUILD_DIR}"
}

trap cleanup EXIT

set -e
set -x

# Get the latest pi-gen code.
wget https://github.com/RPi-Distro/pi-gen/archive/refs/heads/bookworm-arm64.zip -O /var/tmp/bookworm-arm64.zip
unzip /var/tmp/bookworm-arm64.zip -d /var/tmp
mv /var/tmp/pi-gen-bookworm-arm64 /var/tmp/wrolpi-build-pi-gen

# Copy the configuration and build files into the pi-gen directory.
cp "${SCRIPT_DIR}/config.txt" "${BUILD_DIR}/config.txt"
rsync -a "${SCRIPT_DIR}"/stage2/* "${BUILD_DIR}/stage2/"

# We only need to build the Lite and Desktop images.
rm "${BUILD_DIR}"/stage*/EXPORT*
#echo 'IMG_SUFFIX="-lite"' > "${BUILD_DIR}/stage2/EXPORT_IMAGE"
echo 'IMG_SUFFIX="-desktop"' > "${BUILD_DIR}/stage5/EXPORT_IMAGE"

# Build the images.
(cd "${BUILD_DIR}" && time nice -n 18 "${BUILD_DIR}"/build.sh -c "${BUILD_DIR}"/config.txt | \
  tee "${SCRIPT_DIR}"/build.log)

grep "00-run-chroot.sh completed" "${SCRIPT_DIR}/build.log" >/dev/null 2>&1 || (echo "script 0 failed!" && exit 1)
grep "03-run-chroot.sh completed" "${SCRIPT_DIR}/build.log" >/dev/null 2>&1 || (echo "script 3 failed!" && exit 1)
grep "03-run-chroot.sh completed" "${SCRIPT_DIR}/build.log" >/dev/null 2>&1 || (echo "script 3 failed!" && exit 1)
grep "04-run-chroot.sh completed" "${SCRIPT_DIR}/build.log" >/dev/null 2>&1 || (echo "script 4 failed!" && exit 1)

# Move the built images out of the build directory.
#mv "${BUILD_DIR}"/deploy/*lite*xz "${SCRIPT_DIR}"/WROLPi-v"${VERSION}"-aarch64-lite.img.xz
mv "${BUILD_DIR}"/deploy/*desktop*xz "${SCRIPT_DIR}"/WROLPi-v"${VERSION}"-aarch64-desktop.img.xz
chmod 644 "${SCRIPT_DIR}"/*xz
chown -R 1000:1000 "${SCRIPT_DIR}"

rm -rf "${BUILD_DIR}"

set +x

echo "Build completed successfully"
