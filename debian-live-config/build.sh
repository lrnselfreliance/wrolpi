#!/bin/bash
# https://live-team.pages.debian.net/live-manual/html/live-manual/index.en.html

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
BUILD_DIR=/tmp/wrolpi-build-debian

VERSION=$(cat "${SCRIPT_DIR}/../wrolpi/version.txt")

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

if [ ! -f "${SCRIPT_DIR}/config/includes.chroot/opt/wrolpi-blobs/map-db-gis.dump" ]; then
  echo "config/includes.chroot/opt/wrolpi-blobs/map-db-gis.dump does not exist!"
  exit 1
fi

# Clear out old builds.
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

time nice -n 18 lb build 2>&1 | tee "${SCRIPT_DIR}/build.log"

grep "9999-wrolpi.hook.chroot completed" "${SCRIPT_DIR}/build.log" >/dev/null 2>&1 || (echo "build hook failed!" && exit 1)

cp "${BUILD_DIR}"/*iso "${SCRIPT_DIR}/" || (echo "Build failed. No ISOs were found!" && exit 1)
chmod 644 "${SCRIPT_DIR}"/*iso
chown 1000:1000 "${SCRIPT_DIR}"/*iso
DEST="${SCRIPT_DIR}/WROLPi-v${VERSION}-amd64.iso"
[ -f "${DEST}" ] && (echo "Removing conflicting ISO" && rm "${DEST}")
mv "${SCRIPT_DIR}"/*.iso "${DEST}"

echo "Build has completed. ISO output ${DEST}"
