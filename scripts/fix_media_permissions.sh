#!/usr/bin/env bash
# Fix ownership and permissions on the WROLPi media directory so WROLPi can read and write all files.

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

MEDIA_DIRECTORY="/media/wrolpi"

# Source .env override if it exists.
if [ -f /opt/wrolpi/.env ]; then
  # shellcheck disable=SC1091
  source /opt/wrolpi/.env
fi

if [ ! -d "${MEDIA_DIRECTORY}" ]; then
  echo "ERROR: Media directory does not exist: ${MEDIA_DIRECTORY}"
  exit 1
fi

# Detect the filesystem type of the media directory.
fstype=$(findmnt -n -o FSTYPE --target "${MEDIA_DIRECTORY}" 2>/dev/null)

if [[ "${fstype}" == "vfat" || "${fstype}" == "exfat" || "${fstype}" == "ntfs" || "${fstype}" == "fuseblk" ]]; then
  echo "ERROR: ${MEDIA_DIRECTORY} is on a ${fstype} filesystem."
  echo ""
  echo "FAT, exFAT, and NTFS filesystems do not support Unix file permissions."
  echo "Ownership and permissions are controlled by mount options instead."
  echo ""
  echo "To fix permissions, remount the drive with the correct options:"
  echo "  sudo mount -o remount,uid=wrolpi,gid=wrolpi ${MEDIA_DIRECTORY}"
  echo ""
  echo "Or add to /etc/fstab for a permanent fix:"
  echo "  UUID=<your-drive-uuid> ${MEDIA_DIRECTORY} ${fstype} uid=wrolpi,gid=wrolpi,nofail 0 0"
  exit 1
fi

echo "Fixing permissions on ${MEDIA_DIRECTORY}..."

errors=0
dirs_fixed=0
files_fixed=0

# Fix ownership.
if ! chown -R wrolpi:wrolpi "${MEDIA_DIRECTORY}" 2>/dev/null; then
  echo "WARNING: Could not change ownership."
  errors=$((errors + 1))
fi

# Ensure directories have at least u+rwx so they can be listed, traversed, and written to.
count=$(find "${MEDIA_DIRECTORY}" -type d ! -perm -u+rwx -print 2>/dev/null | wc -l)
if [ "$count" -gt 0 ]; then
  find "${MEDIA_DIRECTORY}" -type d ! -perm -u+rwx -exec chmod u+rwx {} + 2>/dev/null || errors=$((errors + 1))
  dirs_fixed=$count
fi

# Ensure files have at least u+rw so they can be read and modified.
count=$(find "${MEDIA_DIRECTORY}" -type f ! -perm -u+rw -print 2>/dev/null | wc -l)
if [ "$count" -gt 0 ]; then
  find "${MEDIA_DIRECTORY}" -type f ! -perm -u+rw -exec chmod u+rw {} + 2>/dev/null || errors=$((errors + 1))
  files_fixed=$count
fi

echo ""
echo "=== Summary ==="
echo "Directories fixed: ${dirs_fixed}"
echo "Files fixed:       ${files_fixed}"
echo "Errors:            ${errors}"

if [ "$errors" -gt 0 ]; then
  echo ""
  echo "Some operations failed."
fi

echo ""
echo "Done."
