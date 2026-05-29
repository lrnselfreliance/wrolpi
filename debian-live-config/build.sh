#!/bin/bash
# Build the WROLPi Debian Live + installer ISO.
#
# Output: an iso-hybrid image that boots into a full WROLPi system on any
# x86 PC.  Users can run WROLPi directly off the USB (persistence partition
# created on first boot) or install to disk via the Calamares launcher on
# the desktop.  Calamares wiring lands in phase 2; phase 1 ships the
# live-only flow.
#
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

# Get version from the target git branch (not local checkout) so output
# filename matches actual content.  Strip whitespace so stray newlines or
# spaces in version.txt do not corrupt the lb config metadata strings.
VERSION=$(curl -sL "https://raw.githubusercontent.com/lrnselfreliance/wrolpi/${BRANCH}/wrolpi/version.txt" | tr -d '[:space:]')
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

# Clear out old builds.  Strip immutable flag from blob files first — the
# chroot hook applies chattr +i to /opt/wrolpi-blobs/*; without removing
# that here, rm -rf leaves them behind and the next lb build's
# chroot_includes_after_packages rsync fails with "Operation not permitted"
# trying to overwrite them.
if [ -d "${BUILD_DIR}" ]; then
  find "${BUILD_DIR}" -path '*/opt/wrolpi-blobs/*' -type f -exec chattr -i {} + 2>/dev/null || true
  rm -rf "${BUILD_DIR}"
fi
mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}" || (echo "Work directory must exist" && exit 1)
set -e

# Live + Debian Installer.  The installer is the stock Debian d-i with
# `--debian-installer live`, which copies the running squashfs onto the
# target disk (much faster than a network-based install) and presents the
# usual graphical/text installer flow.  GRUB gets "Install" + "Graphical
# install" + "Live" entries.  noswap prevents the live system from
# activating swap partitions found on the host machine's internal disks.
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
 --bootappend-live "boot=live components quiet splash noswap persistence persistence-storage=filesystem persistence-media=removable persistence-label=persistence live-config.username=wrolpi live-config.user-fullname=WROLPi live-config.hostname=wrolpi" \
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

# pipefail so an lb build failure isn't masked by tee's success exit code.
set -o pipefail
time nice -n 18 lb build 2>&1 | tee "${SCRIPT_DIR}/build.log"
set +o pipefail

grep "9999-wrolpi.hook.chroot completed" "${SCRIPT_DIR}/build.log" >/dev/null 2>&1 || (echo "build hook failed!" && exit 1)

cp "${BUILD_DIR}"/*iso "${SCRIPT_DIR}/" || (echo "Build failed. No ISOs were found!" && exit 1)
chmod 644 "${SCRIPT_DIR}"/*iso
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "${SCRIPT_DIR}"/*iso
DEST="${SCRIPT_DIR}/WROLPi-v${VERSION}-amd64.iso"
[ -f "${DEST}" ] && (echo "Removing conflicting ISO" && rm "${DEST}")
mv "${SCRIPT_DIR}"/*.iso "${DEST}"

# Sanity-check the resulting ISO before declaring success, so a truncated or
# corrupt build never ships.
MIN_ISO_BYTES=$((1024 * 1024 * 1024))   # 1 GiB floor; a real ISO is ~3 GiB.
ISO_BYTES=$(stat -c%s "${DEST}")
if [ "${ISO_BYTES}" -lt "${MIN_ISO_BYTES}" ]; then
  echo "ERROR: ISO is only ${ISO_BYTES} bytes (< ${MIN_ISO_BYTES}); build likely truncated." >&2
  exit 1
fi
# The ISO 9660 primary volume descriptor carries the "CD001" magic at byte
# offset 32769.  It is present even in iso-hybrid images, where `file` reports
# the leading MBR instead.
if [ "$(dd if="${DEST}" bs=1 skip=32769 count=5 2>/dev/null)" != "CD001" ]; then
  echo "ERROR: ${DEST} is not a valid ISO 9660 image (missing CD001 magic)." >&2
  exit 1
fi
# Cross-check with blkid when available.
if command -v blkid >/dev/null 2>&1; then
  ISO_FSTYPE=$(blkid -o value -s TYPE "${DEST}" 2>/dev/null || true)
  if [ -n "${ISO_FSTYPE}" ] && [ "${ISO_FSTYPE}" != "iso9660" ]; then
    echo "ERROR: blkid reports filesystem '${ISO_FSTYPE}', expected iso9660." >&2
    exit 1
  fi
fi
echo "ISO sanity checks passed ($(numfmt --to=iec "${ISO_BYTES}" 2>/dev/null || echo "${ISO_BYTES} bytes"), iso9660)."

echo "Build has completed. ISO output ${DEST}"
