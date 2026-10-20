#!/bin/bash
# Check a built WROLPi ISO for problems that only show up after the Debian
# installer has run.  build.sh runs this on every build; it can also be run by
# hand against any ISO:
#
#   ./check-iso.sh WROLPi-v0.30.0-beta-amd64.iso
#
# Requires bsdtar (libarchive-tools), isoinfo (genisoimage) and unsquashfs
# (squashfs-tools).

ISO=$1
if [ -z "${ISO}" ] || [ ! -f "${ISO}" ]; then
  echo "Usage: check-iso.sh ISO" >&2
  exit 1
fi

for tool in bsdtar:libarchive-tools isoinfo:genisoimage unsquashfs:squashfs-tools; do
  if ! command -v "${tool%%:*}" >/dev/null 2>&1; then
    echo "ERROR: ${tool%%:*} is required (apt install ${tool#*:})." >&2
    exit 1
  fi
done

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

# The Debian installer creates the user it asks for only if no user with a UID
# from 1000 to 59999 exists (user-setup's is_system_user); otherwise it skips
# that user silently.  wrolpi must be a system account (UID < 1000), as on
# every other WROLPi deployment.
SQUASHFS_LBA=$(isoinfo -i "${ISO}" -R -l 2>/dev/null \
  | awk '/ filesystem\.squashfs/ {sub(/.*\[ */, ""); print $1; exit}')
if [ -z "${SQUASHFS_LBA}" ] \
    || ! unsquashfs -o $((SQUASHFS_LBA * 2048)) -cat "${ISO}" etc/passwd > "${TMP}/passwd" 2>/dev/null; then
  echo "ERROR: could not read /etc/passwd from live/filesystem.squashfs in ${ISO}." >&2
  exit 1
fi
if awk -F: '$3 >= 1000 && $3 < 60000 {found=1} END {exit !found}' "${TMP}/passwd"; then
  echo "ERROR: the Debian installer would not create the user it asks for, because these users exist:" >&2
  awk -F: '$3 >= 1000 && $3 < 60000 {print "  " $1 " (UID " $3 ")"}' "${TMP}/passwd" >&2
  echo "Create them with useradd --system." >&2
  FAILED=1
fi

# A Live USB must come back on its own after a reboot or power loss: the boot
# menus must boot their default entry after a timeout (0 waits forever).
if ! extract boot/grub/config.cfg || ! grep -qE '^set timeout=[1-9]' "${TMP}/config.cfg"; then
  echo "ERROR: the GRUB (UEFI) boot menu has no timeout; a Live USB would wait at it forever." >&2
  FAILED=1
fi
if extract isolinux/isolinux.cfg && ! grep -qE '^timeout [1-9]' "${TMP}/isolinux.cfg"; then
  echo "ERROR: the ISOLINUX (BIOS) boot menu has no timeout; a Live USB would wait at it forever." >&2
  FAILED=1
fi

# INSTALL.md and the onboarding wizard send people to wrolpi.local, which only
# resolves if the WROLPi advertises its hostname over mDNS (avahi-daemon), and
# only resolves on the WROLPi's own desktop with libnss-mdns.
for pkg in avahi-daemon libnss-mdns; do
  if ! grep -qE "^${pkg}(:[a-z0-9]+)?[[:space:]]" "${TMP}/filesystem.packages"; then
    echo "ERROR: ${pkg} is not installed; wrolpi.local would not resolve." >&2
    FAILED=1
  fi
done

# The installer should default the hostname to wrolpi (wrolpi.local), via the
# preseed live-build copies into each installer initrd.
for initrd in install/initrd.gz install/gtk/initrd.gz; do
  if ! bsdtar -xOf "${ISO}" "${initrd}" 2>/dev/null | bsdtar -xOf - preseed.cfg 2>/dev/null \
      | grep -q '^d-i netcfg/get_hostname string wrolpi$'; then
    echo "ERROR: ${initrd} does not preseed the hostname wrolpi." >&2
    FAILED=1
  fi
done

if [ "${FAILED}" -ne 0 ]; then
  exit 1
fi
echo "ISO install checks passed."
