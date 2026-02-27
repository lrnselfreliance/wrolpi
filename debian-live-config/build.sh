#!/bin/bash
# https://live-team.pages.debian.net/live-manual/html/live-manual/index.en.html

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
BUILD_DIR=/var/tmp/wrolpi-build-debian

Help() {
  echo "Build WROLPi Debian Live ISO image."
  echo
  echo "Syntax: build.sh [-h] [-b BRANCH]"
  echo "options:"
  echo "h     Print this help."
  echo "b     Build from this git BRANCH (default: 'release')."
  echo
}

BRANCH="release"
while getopts ":hb:" option; do
  case $option in
  h) Help; exit ;;
  b) BRANCH="${OPTARG}" ;;
  *) echo "Error: Invalid option"; exit 1 ;;
  esac
done

# Get version from the target git branch (not local checkout) so output filename matches actual content.
VERSION=$(curl -sL "https://raw.githubusercontent.com/lrnselfreliance/wrolpi/${BRANCH}/wrolpi/version.txt")
if [ -z "${VERSION}" ]; then
  echo "ERROR: Could not fetch version from branch '${BRANCH}'"
  exit 1
fi
echo "Building WROLPi version: ${VERSION} from branch: ${BRANCH}"

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

if [ ! -f "${SCRIPT_DIR}/config/includes.chroot/opt/wrolpi-blobs/map-db-gis.dump" ]; then
  echo "config/includes.chroot/opt/wrolpi-blobs/map-db-gis.dump does not exist!"
  exit 1
fi

# Validate dump file format - must be PostgreSQL custom format (PGDMP magic)
DUMP_FILE="${SCRIPT_DIR}/config/includes.chroot/opt/wrolpi-blobs/map-db-gis.dump"
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

# Clear out old builds.
# Remove immutable attribute from protected files before cleanup
chattr -i "${BUILD_DIR}"/chroot/opt/wrolpi-blobs/* 2>/dev/null || :
[ -d "${BUILD_DIR}" ] && rm -rf "${BUILD_DIR}"
mkdir "${BUILD_DIR}"
cd "${BUILD_DIR}" || (echo "Work directory must exist" && exit 1)
set -e

lb config \
 --binary-images iso-hybrid \
 --mode debian \
 --architectures amd64 \
 --linux-flavours amd64 \
 --distribution bookworm \
 --debian-installer live \
 --debian-installer-gui true \
 --archive-areas "main contrib non-free non-free-firmware" \
 --updates true \
 --security true \
 --apt-recommends false \
 --firmware-binary true \
 --firmware-chroot true \
 --win32-loader false \
 --checksums sha512 \
 --clean \
 --color \
 --linux-packages "linux-image linux-headers" \
 --memtest memtest86+ \
 --iso-volume "WROLPi v${VERSION}" \
 --iso-application "WROLPi v${VERSION}" \
 --iso-preparer WROLPi \
 --iso-publisher https://wrolpi.org

rsync -a "${SCRIPT_DIR}/config" "${BUILD_DIR}/"

# Write branch config for hook script.
echo "${BRANCH}" > "${BUILD_DIR}/config/includes.chroot/opt/wrolpi-branch"

time nice -n 18 lb build 2>&1 | tee "${SCRIPT_DIR}/build.log"

grep "9999-wrolpi.hook.chroot completed" "${SCRIPT_DIR}/build.log" >/dev/null 2>&1 || (echo "build hook failed!" && exit 1)

cp "${BUILD_DIR}"/*iso "${SCRIPT_DIR}/" || (echo "Build failed. No ISOs were found!" && exit 1)
chmod 644 "${SCRIPT_DIR}"/*iso
chown 1000:1000 "${SCRIPT_DIR}"/*iso
DEST="${SCRIPT_DIR}/WROLPi-v${VERSION}-amd64.iso"
[ -f "${DEST}" ] && (echo "Removing conflicting ISO" && rm "${DEST}")
mv "${SCRIPT_DIR}"/*.iso "${DEST}"

echo "Build has completed. ISO output ${DEST}"
