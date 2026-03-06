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

echo "Fixing permissions on ${MEDIA_DIRECTORY}..."

errors=0
dirs_fixed=0
files_fixed=0

# Fix ownership. FAT/exFAT filesystems do not support chown, so warn and continue.
if ! chown -R wrolpi:wrolpi "${MEDIA_DIRECTORY}" 2>/dev/null; then
  echo "WARNING: Could not change ownership (filesystem may not support Unix ownership, e.g. FAT/exFAT)."
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
  echo "Some operations failed. This may be expected on FAT/exFAT filesystems."
fi

echo ""
echo "Done."
