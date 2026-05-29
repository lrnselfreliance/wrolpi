#!/usr/bin/env bash
# WROLPi USB upgrade + install tool.
#
# Run from any modern Linux host.  Plug the target USB drive in, then:
#
#   sudo ./wrolpi-usb.sh upgrade <iso> <device>
#     Replace the boot partition of an existing WROLPi USB with a new
#     ISO.  The persistence partition (your library + database +
#     configuration) is preserved.
#
#   sudo ./wrolpi-usb.sh install
#     Converting an existing data drive into a WROLPi USB in place is
#     NOT supported.  Running this prints the supported procedure:
#     back up your data, flash the whole drive with the ISO, boot once
#     to create the persistence partition, then restore your data.
#
# The upgrade command saves the current partition table to
# /tmp/wrolpi-usb-<device>-<timestamp>.sfdisk before any destructive
# operation, and refuses to run on non-removable disks.

set -euo pipefail

HEADROOM_BYTES=$((8 * 1024 * 1024 * 1024))   # 8 GiB; mirrors wrolpi-bootstrap.sh

# ---------------------------------------------------------------------------

die()  { echo "ERROR: $*" >&2; exit 1; }
warn() { echo "WARN: $*" >&2; }
info() { echo "$*"; }

usage() {
  sed -n '2,/^$/p' "$0" | sed 's|^# \{0,1\}||'
  exit 0
}

require_root() {
  [ "$(id -u)" -eq 0 ] || die "this script must run as root (try sudo)"
}

require_tool() {
  command -v "$1" >/dev/null 2>&1 || die "missing required tool: $1"
}

confirm() {
  echo
  echo "$1"
  read -r -p "Type 'yes' to continue, anything else to abort: " ans
  [ "$ans" = "yes" ] || die "aborted by user"
}

backup_partition_table() {
  local dev=$1
  local stamp; stamp=$(date +%Y%m%d-%H%M%S)
  local out=/tmp/wrolpi-usb-$(basename "$dev")-${stamp}.sfdisk
  sfdisk -d "$dev" > "$out"
  info "Saved current partition table to $out"
  info "  (restore with: sudo sfdisk $dev < $out)"
}

sanity_check_device() {
  local dev=$1
  [ -b "$dev" ] || die "$dev is not a block device"

  # Refuse non-removable disks unless explicitly forced.  Avoids the
  # common foot-gun of typing the OS disk by mistake.
  local removable
  removable=$(lsblk -dno RM "$dev" 2>/dev/null || echo 0)
  if [ "$removable" != "1" ]; then
    die "$dev is not a removable disk.  If this really is the target, " \
        "use a Linux box where it shows as removable."
  fi

  # Anything currently mounted?  We need it idle.
  local mounted
  mounted=$(lsblk -no MOUNTPOINTS "$dev" 2>/dev/null | grep -v '^$' || true)
  if [ -n "$mounted" ]; then
    info "Mounted children of $dev:"
    echo "$mounted" | sed 's/^/  /'
    confirm "These mounts will be unmounted before we proceed."
    for child in $(lsblk -lnpo NAME "$dev" | tail -n +2); do
      umount "$child" 2>/dev/null || true
    done
    # Re-check: a busy partition (open file handle, daemon, etc.) will
    # have swallowed our umount silently.  dd-ing a device whose
    # partition is still mounted corrupts the live filesystem.  Bail
    # loudly before any destructive operation.
    mounted=$(lsblk -no MOUNTPOINTS "$dev" 2>/dev/null | grep -v '^$' || true)
    if [ -n "$mounted" ]; then
      info "Still mounted after umount attempt:"
      echo "$mounted" | sed 's/^/  /'
      die "could not unmount $dev (a partition is in use).  Close any " \
          "open file handles or run `sudo lsof $dev*` to find them, then retry."
    fi
  fi
}

partition_sector_range() {
  # Print start and size (in 512-byte sectors) of the partition.
  # Args: <device> <partition node, e.g. /dev/sdb3>
  #
  # sfdisk -d output pads values with whitespace ("start=          64,")
  # which confuses naive awk field-splitting; use sed to pull both numbers
  # out at once.
  local dev=$1 part=$2
  sfdisk -d "$dev" \
    | sed -n "s|^${part} *: *start= *\([0-9]\+\), *size= *\([0-9]\+\).*|\1 \2|p"
}

# ---------------------------------------------------------------------------

cmd_upgrade() {
  local iso=$1
  local dev=$2
  [ -f "$iso" ] || die "ISO not found: $iso"
  sanity_check_device "$dev"

  require_tool dd
  require_tool sfdisk
  require_tool partx
  require_tool blkid
  require_tool lsblk
  require_tool udevadm

  # Locate the persistence partition on the target device.
  local persist_part=""
  for part in $(lsblk -lnpo NAME "$dev" | tail -n +2); do
    if [ "$(lsblk -no LABEL "$part" 2>/dev/null)" = "persistence" ]; then
      persist_part=$part
      break
    fi
  done
  [ -n "$persist_part" ] || die "no partition labelled 'persistence' found on $dev"

  local sector_info
  sector_info=$(partition_sector_range "$dev" "$persist_part")
  [ -n "$sector_info" ] || die "could not read sector range for $persist_part"
  local persist_start persist_size
  read -r persist_start persist_size <<<"$sector_info"

  local iso_size; iso_size=$(stat -c %s "$iso")
  local headroom_bytes=$((persist_start * 512 - iso_size))

  info "ISO:               $iso ($(numfmt --to=iec --suffix=B "$iso_size"))"
  info "Target device:     $dev ($(lsblk -no MODEL,SIZE "$dev" | head -1))"
  info "Persistence:       $persist_part starts at sector $persist_start ($(numfmt --to=iec --suffix=B "$((persist_start * 512))"))"
  info "Headroom for ISO:  $(numfmt --to=iec --suffix=B "$((persist_start * 512))")"
  # numfmt treats a leading dash as an option flag.  Format the absolute
  # value and prefix the sign manually so a negative headroom doesn't
  # crash the script under `set -euo pipefail` before the descriptive
  # error message below has a chance to print.
  if [ "$headroom_bytes" -ge 0 ]; then
    info "Headroom vs ISO:   $(numfmt --to=iec --suffix=B "$headroom_bytes") free"
  else
    info "Headroom vs ISO:   -$(numfmt --to=iec --suffix=B "$(( -headroom_bytes ))") (ISO is too large)"
  fi

  if [ "$headroom_bytes" -lt 0 ]; then
    cat >&2 <<EOF

ERROR: the new ISO is larger than the headroom on this USB.

  USBs flashed from older WROLPi releases (before the 8 GiB-headroom
  change) cannot upgrade in place — the persistence partition starts
  immediately after the ISO partition, with no room for a bigger ISO.

  To upgrade, you'll need to:
    1. Back up /media/wrolpi/ to another drive.
    2. Re-flash the new ISO from scratch with dd or Etcher.
    3. Restore /media/wrolpi/ from the backup.

  Future versions flashed from a release ≥ 0.22 reserve 8 GiB of
  headroom and won't have this problem.
EOF
    exit 2
  fi

  backup_partition_table "$dev"

  confirm "About to overwrite the boot partition on $dev with $iso.
The persistence partition ($persist_part) data will be preserved.
This operation cannot be undone."

  info "Writing ISO to $dev..."
  dd if="$iso" of="$dev" bs=4M status=progress conv=fsync
  sync

  info "Re-adding persistence partition entry..."
  # The new ISO's partition table only has the ISO's own partitions.
  # Re-append the persistence entry at its original sector range; the
  # data on disk is still intact.
  echo "start=$persist_start, size=$persist_size, type=83" \
    | sfdisk --append --no-reread --force "$dev"
  partx -u "$dev" 2>/dev/null || true
  udevadm settle || true

  # Verify the persistence partition is reachable + still labelled.
  sleep 1
  local found_label
  found_label=$(blkid -L persistence 2>/dev/null || true)
  if [ -z "$found_label" ]; then
    warn "could not find a 'persistence' label after re-adding the partition."
    warn "data should still be present at sector $persist_start; you may need"
    warn "to re-label with: sudo e2label <partition> persistence"
  else
    info "Persistence label resolved to: $found_label"
  fi

  info "Done.  Eject the USB and boot it to verify."
}

cmd_install() {
  # In-place conversion of an existing data drive is intentionally not
  # supported.  A WROLPi USB is a dd-flashed iso-hybrid image with its
  # persistence partition appended on first boot; there is no safe,
  # filesystem-agnostic way to graft that onto a drive that is already
  # full of the user's data without risking it.  Point the user at the
  # supported backup -> flash -> restore path instead.
  cat >&2 <<'EOF'
Converting an existing drive into a WROLPi USB in place is not supported.

A WROLPi USB is created by flashing the whole drive with the ISO, which
erases everything already on it.  To turn a drive you already use into a
WROLPi USB without losing your files:

  1. Back up everything on the drive to another disk.
  2. Flash the whole drive with the ISO (this erases it):
       sudo dd if=<iso> of=<device> bs=4M status=progress conv=fsync
     (or use Etcher / Rufus / Raspberry Pi Imager)
  3. Boot the drive once.  WROLPi creates its persistence partition and
     sets itself up on first boot.
  4. Copy your backed-up data into /media/wrolpi/ on the running system,
     then let WROLPi refresh/repair so it indexes the restored files.

Once a drive has been set up this way, future ISO upgrades preserve your
library and are done with:

  sudo ./wrolpi-usb.sh upgrade <iso> <device>
EOF
  exit 2
}

# ---------------------------------------------------------------------------

main() {
  case "${1:-}" in
    upgrade)
      shift
      [ $# -eq 2 ] || { usage; exit 1; }
      require_root
      cmd_upgrade "$@"
      ;;
    install)
      # No args required: install only prints the supported procedure
      # and exits.  Don't require root or an iso/device.
      cmd_install
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      echo "Unknown command: $1" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
