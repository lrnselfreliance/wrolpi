#!/bin/bash
# https://github.com/RPI-Distro/pi-gen

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
BUILD_DIR=/tmp/wrolpi-build-pi-gen

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

set -e
set -x

# Clear out old builds.
[ -d "${BUILD_DIR}" ] && rm -rf "${BUILD_DIR}"
mkdir "${BUILD_DIR}"

# We need the arm64 branch for modern RPi.
git clone --branch arm64 https://github.com/RPI-Distro/pi-gen.git "${BUILD_DIR}"

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

grep "02-run.sh completed" "${SCRIPT_DIR}/build.log" >/dev/null 2>&1 || (echo "script 2 failed!" && exit 1)
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
