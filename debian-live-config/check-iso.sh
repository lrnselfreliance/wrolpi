#!/bin/bash
# Check a built WROLPi ISO for problems that only show up after the Debian
# installer has run.  build.sh runs this on every build; it can also be run by
# hand against any ISO:
#
#   ./check-iso.sh WROLPi-v0.30.0-beta-amd64.iso
#
# Requires bsdtar (Debian package libarchive-tools; built into macOS).

ISO=$1
if [ -z "${ISO}" ] || [ ! -f "${ISO}" ]; then
  echo "Usage: check-iso.sh ISO" >&2
  exit 1
fi

if ! command -v bsdtar >/dev/null 2>&1; then
  echo "ERROR: bsdtar is required (apt install libarchive-tools)." >&2
  exit 1
fi

TMP=$(mktemp -d)
trap 'rm -rf "${TMP}"' EXIT

# extract PATH: copy one file out of the ISO into ${TMP}.
extract() {
  bsdtar -xOf "${ISO}" "$1" > "${TMP}/$(basename "$1")" 2>/dev/null
}

FAILED=0

# The package manifest is always present; failing to read it means the ISO (or
# bsdtar) is broken, and the checks below would pass vacuously.
if ! extract live/filesystem.packages; then
  echo "ERROR: could not read /live/filesystem.packages from ${ISO}." >&2
  exit 1
fi

# The Debian installer (finish-install.d/14remove-live-packages) purges every
# package listed in filesystem.packages-remove.  live-build lists every package
# installed after the package-lists install pass -- including anything a chroot
# hook installs with apt.  WROLPi has no live-only packages, so the list must not
# exist.  Install packages through config/package-lists/ (and config/archives/
# for third-party repos) instead of apt-get in a hook.
if extract live/filesystem.packages-remove && [ -s "${TMP}/filesystem.packages-remove" ]; then
  echo "ERROR: the Debian installer would remove these packages from an installed WROLPi:" >&2
  sed 's/^/  /' "${TMP}/filesystem.packages-remove" >&2
  echo "Install them via config/package-lists/ instead of a chroot hook." >&2
  FAILED=1
fi

if [ "${FAILED}" -ne 0 ]; then
  exit 1
fi
echo "ISO install checks passed."
