#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
BUILD_DIR=/tmp/wrolpi-build

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
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
 --cache true \
 --apt-recommends false \
 --firmware-binary true \
 --firmware-chroot true \
 --win32-loader false \
 --checksums sha512 \
 --clean \
 --color \
 --iso-preparer WROLPi \
 --iso-publisher https://wrolpi.org

rsync -a "${SCRIPT_DIR}/config" "${BUILD_DIR}/"

lb build 2>&1 | tee "${SCRIPT_DIR}/build.log"

cp "${BUILD_DIR}"/live*iso "${SCRIPT_DIR}/" || (echo "Build failed. No ISOs were found!" && exit 1)
chmod 644 "${SCRIPT_DIR}"/*iso
