#!/bin/bash
# https://github.com/RPI-Distro/pi-gen

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
BUILD_DIR=/var/tmp/wrolpi-build-pi-gen

Help() {
  echo "Build WROLPi Raspberry Pi OS image."
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

    # Remove immutable attribute from protected files before cleanup
    chattr -i "${BUILD_DIR}"/work/*/stage*/rootfs/opt/wrolpi-blobs/* 2>/dev/null || :

    # Final safety net – remove the whole build tree
    rm -rf "${BUILD_DIR}"
}

trap cleanup EXIT

set -e
set -x

# Cache directory for downloaded blobs (persists across builds).
BLOB_CACHE="${SCRIPT_DIR}/stage2/04-wrolpi/files"
mkdir -p "${BLOB_CACHE}"

# Download map fonts (skip if cached).
if [ ! -f "${BLOB_CACHE}/map-fonts.tar.gz" ]; then
  echo "Downloading map fonts..."
  mkdir -p /tmp/map-fonts-dl
  curl -fsSL https://github.com/protomaps/basemaps-assets/archive/refs/heads/main.tar.gz \
    | tar -xz --strip-components=1 -C /tmp/map-fonts-dl basemaps-assets-main/fonts
  tar -czf "${BLOB_CACHE}/map-fonts.tar.gz" -C /tmp/map-fonts-dl fonts
  rm -rf /tmp/map-fonts-dl
fi
[[ -f "${BLOB_CACHE}/map-fonts.tar.gz" && -s "${BLOB_CACHE}/map-fonts.tar.gz" ]] || \
  (echo "ERROR: Failed to download map fonts!" && exit 1)

# Download map overview (skip if cached).
if [ ! -f "${BLOB_CACHE}/map-overview.pmtiles" ]; then
  echo "Downloading map overview..."
  curl -fsSL https://wrolpi.nyc3.cdn.digitaloceanspaces.com/maps/map-overview.pmtiles \
    -o "${BLOB_CACHE}/map-overview.pmtiles"
fi
[[ -f "${BLOB_CACHE}/map-overview.pmtiles" && -s "${BLOB_CACHE}/map-overview.pmtiles" ]] || \
  (echo "ERROR: Failed to download map overview!" && exit 1)

# Get the latest pi-gen code.
wget https://github.com/RPi-Distro/pi-gen/archive/refs/heads/bookworm-arm64.zip -O /var/tmp/bookworm-arm64.zip
unzip /var/tmp/bookworm-arm64.zip -d /var/tmp
mv /var/tmp/pi-gen-bookworm-arm64 /var/tmp/wrolpi-build-pi-gen

# Copy the configuration and build files into the pi-gen directory.
cp "${SCRIPT_DIR}/config.txt" "${BUILD_DIR}/config.txt"
echo "export WROLPI_BRANCH=${BRANCH}" >> "${BUILD_DIR}/config.txt"
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

set +x

echo "Build completed successfully"
