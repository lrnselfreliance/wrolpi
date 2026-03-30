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

# Write branch config for hook script.
mkdir -p "${BUILD_DIR}/config/includes.chroot/opt/wrolpi-blobs"
echo "${BRANCH}" > "${BUILD_DIR}/config/includes.chroot/opt/wrolpi-branch"

# Cache directory for downloaded blobs (persists across builds).
BLOB_CACHE="${SCRIPT_DIR}/files"
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

# Copy cached blobs into the live image.
cp "${BLOB_CACHE}/map-fonts.tar.gz" "${BUILD_DIR}/config/includes.chroot/opt/wrolpi-blobs/"
cp "${BLOB_CACHE}/map-overview.pmtiles" "${BUILD_DIR}/config/includes.chroot/opt/wrolpi-blobs/"

time nice -n 18 lb build 2>&1 | tee "${SCRIPT_DIR}/build.log"

grep "9999-wrolpi.hook.chroot completed" "${SCRIPT_DIR}/build.log" >/dev/null 2>&1 || (echo "build hook failed!" && exit 1)

cp "${BUILD_DIR}"/*iso "${SCRIPT_DIR}/" || (echo "Build failed. No ISOs were found!" && exit 1)
chmod 644 "${SCRIPT_DIR}"/*iso
chown 1000:1000 "${SCRIPT_DIR}"/*iso
DEST="${SCRIPT_DIR}/WROLPi-v${VERSION}-amd64.iso"
[ -f "${DEST}" ] && (echo "Removing conflicting ISO" && rm "${DEST}")
mv "${SCRIPT_DIR}"/*.iso "${DEST}"

echo "Build has completed. ISO output ${DEST}"
