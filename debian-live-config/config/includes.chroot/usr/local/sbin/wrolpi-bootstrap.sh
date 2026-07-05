#!/usr/bin/env bash
# WROLPi bootstrap — runs at every boot via wrolpi-bootstrap.service.
# Idempotent throughout.  Works in all four deployment shapes:
#
# 1. Live USB (direct), first boot.  No persistence partition exists.
#    This script creates one in the free space at the end of the boot
#    drive, formats it as ext4 (label `persistence`), writes a
#    persistence.conf so future boots pick it up automatically via
#    live-boot, bind-mounts the persistence root over /media/wrolpi,
#    creates the Postgres cluster under /media/wrolpi/config/postgresql/,
#    runs initialize_api_db.sh, and enables the WROLPi runtime services.
#
# 2. Live USB (direct), subsequent boot.  live-boot's initramfs has
#    already applied the /media/wrolpi bind mount from persistence.conf.
#    Cluster and DB already exist.  Most steps no-op; we always
#    regenerate the leaf TLS cert and ensure services are enabled.
#
# 3. Live USB (loop / Ventoy / multiboot).  The ISO is loop-mounted by a
#    multiboot tool, so we cannot safely write a new partition to the
#    underlying disk (it's the user's Ventoy stick, not a blank target).
#    /media/wrolpi is backed by tmpfs and everything runs from RAM.  All
#    user data is lost on reboot.  Surfaced to the user via the
#    first-boot zenity dialog.
#
# 4. Installed.  No live medium present; partition-creation branch is
#    skipped.  /media/wrolpi is mounted via /etc/fstab on an external
#    drive, or is a plain directory on the root filesystem if the user
#    installed without one.  Postgres lives at the normal Debian paths on
#    the root filesystem: the bind-mounts are for live boots only, where
#    the root filesystem is ephemeral.  An installed system's primary
#    drive may be NTFS/exFAT, which cannot host a Postgres data
#    directory at all.

set -euo pipefail

log() { echo "[wrolpi-bootstrap] $*"; }

# Show progress on the Plymouth splash so the user sees what's happening
# during the 30-60s first-boot work.  Plymouth is up between initramfs and
# lightdm starting; we block lightdm via systemd ordering, so the splash
# owns the screen for our entire run.  Falls back to log-only if Plymouth
# isn't active (e.g. running this script manually over SSH).
progress() {
  plymouth display-message --text="$1" 2>/dev/null || true
  log "$1"
}

# Accumulate human-readable notes about anything non-trivial we did this
# boot.  If anything ends up in $SUMMARY by end-of-run we write it to a
# file under /tmp/ that the wrolpi user's XFCE autostart picks up to show
# a zenity dialog (see /usr/local/bin/wrolpi-firstboot-notify).  /tmp is
# tmpfs so the file is naturally per-boot; subsequent uneventful boots
# show no dialog.
SUMMARY=""
SUMMARY_FILE=/tmp/wrolpi-firstboot-summary.txt
note_action() { SUMMARY="${SUMMARY}- $1
"; }

progress "Preparing WROLPi..."

# --- Detect deployment mode ---------------------------------------------
# Three mutually-exclusive shapes:
#
#   direct       Live USB flashed with dd/Raspberry Pi Imager: the ISO partition is a
#                real partition on a real disk.  Create + manage a
#                persistence partition on that disk.
#
#   loop         Live medium is a loop or device-mapper node — typical
#                of Ventoy, YUMI, Easy2Boot, GLIM, AIO Boot, etc.  The
#                underlying block device is the user's data drive; we
#                must NOT try to sfdisk-append a partition onto it.
#                Run ephemerally: /media/wrolpi backed by tmpfs, lost
#                on reboot.
#
#   installed    No live medium at all.  Skip partition logic entirely;
#                /media/wrolpi is either on /etc/fstab or a plain dir
#                on the root filesystem.

MODE=installed
BOOT_DRIVE=""
LIVE_MEDIUM=""
for mp in /usr/lib/live/mount/medium /run/live/medium /lib/live/mount/medium; do
  if part=$(findmnt -nr -o SOURCE "$mp" 2>/dev/null) && [ -n "$part" ]; then
    LIVE_MEDIUM=$part
    case "$part" in
      /dev/sd*|/dev/nvme*|/dev/mmcblk*|/dev/vd*|/dev/xvd*|/dev/hd*)
        # Real partitions on real (or virtual) disks: SCSI/USB (sd*),
        # NVMe, SD/eMMC (mmcblk*), VirtIO (vd*), Xen (xvd*), legacy
        # IDE (hd*).  A blank VM disk imaged with the ISO can safely
        # hold a persistence partition, so treat virtual disks as direct
        # rather than letting them fall through to the ephemeral default.
        MODE=direct
        BOOT_DRIVE="/dev/$(lsblk -no PKNAME "$part")"
        log "live medium $part on $BOOT_DRIVE (mode: direct)"
        ;;
      /dev/loop*|/dev/dm-*|/dev/mapper/*)
        MODE=loop
        log "live medium $part is a loop/dm device (mode: loop — ephemeral)"
        ;;
      *)
        MODE=loop
        log "live medium $part has unrecognised shape (mode: loop — safe default)"
        ;;
    esac
    break
  fi
done

if [ "$MODE" = "installed" ]; then
  log "no live medium detected — running in Installed mode"
fi

# --- Find or create persistence partition (direct mode only) ------------

if [ "$MODE" = "direct" ]; then
  PERSIST_PART=$(blkid -L persistence 2>/dev/null || true)
  if [ -z "$PERSIST_PART" ]; then
    progress "Creating persistence partition on $BOOT_DRIVE..."
    # Compute next 1-MiB-aligned start sector after the highest-ending
    # existing partition.  We need MAX(start+size), not LAST: iso-hybrid
    # layouts list a small ESP (sdb2) AFTER the main data partition
    # (sdb1) in sfdisk -d output even though sdb1 ends much later on
    # disk.  Parse via sed because sfdisk -d pads values with spaces
    # ("start=          64,") which breaks naive awk.
    LAST_END=$(sfdisk -d "$BOOT_DRIVE" \
      | sed -n 's|^/dev/[^ ]* *: *start= *\([0-9]\+\), *size= *\([0-9]\+\).*|\1 \2|p' \
      | awk '{e=$1+$2; if(e>m) m=e} END{print m+0}')
    if [ "${LAST_END:-0}" -lt 1 ]; then
      log "ERROR: failed to compute LAST_END from $BOOT_DRIVE partition table"
      exit 1
    fi
    # Reserve 8 GiB of unused space between the ISO partition and the new
    # persistence partition.  The `wrolpi-usb.sh upgrade` tool overwrites
    # the ISO partition with a (potentially larger) new ISO; without
    # headroom, growth past the current ISO size would clobber the
    # persistence partition's data.  8 GiB covers ~2x the current ISO
    # size — enough for several future releases.  Cost: ~8 GiB of
    # persistence space the user doesn't see.
    HEADROOM_SECTORS=$(( 8 * 1024 * 1024 * 1024 / 512 ))
    START=$(( (((LAST_END + HEADROOM_SECTORS) + 2047) / 2048) * 2048 ))
    # --no-reread --force: required because the live medium is mounted from
    # this same drive.  Adding a new partition entry past the mounted one
    # is safe; we use partx -a below to inform the running kernel without
    # forcing a re-read of the whole partition table.
    echo "start=$START, type=83" | sfdisk --append --no-reread --force "$BOOT_DRIVE"
    partx -a "$BOOT_DRIVE" 2>/dev/null || true

    # Identify the new partition by the start sector we just assigned to
    # it.  We deliberately avoid `lsblk | tail -1`: if partx -a or udev
    # haven't registered the new node, that fallback returns the existing
    # last partition (typically the ESP or the live data partition) — and
    # the mkfs.ext4 -F below would wipe it.  Matching on start sector is
    # unambiguous: no existing partition can share it.  Retry up to 5s
    # for udev to settle and the partition node to appear.
    PERSIST_PART=""
    for _i in 1 2 3 4 5; do
      udevadm settle || true
      PERSIST_PART=$(lsblk -lnpo NAME,START "$BOOT_DRIVE" 2>/dev/null \
        | awk -v s="$START" '$2 == s {print $1; exit}')
      [ -n "$PERSIST_PART" ] && [ -b "$PERSIST_PART" ] && break
      PERSIST_PART=""
      sleep 1
    done
    if [ -z "$PERSIST_PART" ] || ! [ -b "$PERSIST_PART" ]; then
      log "ERROR: failed to locate the newly created persistence partition"
      exit 1
    fi
    progress "Formatting $PERSIST_PART as ext4..."
    mkfs.ext4 -L persistence -F "$PERSIST_PART"
    PERSIST_SIZE=$(lsblk -bno SIZE "$PERSIST_PART" 2>/dev/null | numfmt --to=iec --suffix=B || echo "?")
    note_action "Created persistence partition ${PERSIST_PART} (${PERSIST_SIZE}) on ${BOOT_DRIVE}"
  fi

  # Mount the persistence partition + lay out the on-disk structure.
  # /media/wrolpi is bound to /mnt/persistence/wrolpi by either this
  # script (first boot) or live-boot's initramfs (subsequent boots).  The
  # Postgres bind-mounts are managed by THIS script in all cases — see
  # the "Postgres bind-mounts" section below.
  mkdir -p /mnt/persistence
  mountpoint -q /mnt/persistence || mount "$PERSIST_PART" /mnt/persistence
  mkdir -p /mnt/persistence/wrolpi
  chown wrolpi:wrolpi /mnt/persistence/wrolpi

  # persistence.conf: live-boot reads this on boot and applies the bind
  # mount before systemd starts on subsequent boots.  Only /media/wrolpi
  # is here; Postgres bind-mounts are intentionally managed by this
  # script (they live under /media/wrolpi/config/postgresql/ on the
  # mounted /media/wrolpi, so once that bind is in place they are
  # reachable).
  cat > /mnt/persistence/persistence.conf <<'EOF'
/media/wrolpi bind,source=wrolpi
EOF

  # Bind /media/wrolpi on first boot.  live-boot will do this from the
  # initramfs on subsequent boots and the call below is then a no-op.
  if ! mountpoint -q /media/wrolpi; then
    mkdir -p /media/wrolpi
    mount --bind /mnt/persistence/wrolpi /media/wrolpi
  fi
fi

# --- Ephemeral (loop mode) ----------------------------------------------
# Booted via Ventoy / multiboot tool / loop-mounted ISO.  We cannot tell
# which underlying disk is the user's data drive — appending a partition
# would risk corrupting their Ventoy stick or whatever else they had on
# that device.  Run from RAM instead.  Anything written to /media/wrolpi
# vanishes on reboot, but the rest of WROLPi (Postgres bind-mounts,
# config layout, services) works identically.

if [ "$MODE" = "loop" ]; then
  if ! mountpoint -q /media/wrolpi; then
    mkdir -p /media/wrolpi
    # No explicit size= — defaults to half-RAM, plenty for an
    # exploratory session and capped so we can't OOM the box.
    mount -t tmpfs -o mode=0755 tmpfs /media/wrolpi
    log "ephemeral mode: /media/wrolpi is tmpfs (data lost on reboot)"
    # Inside the guard so a manual service restart mid-session (tmpfs
    # already mounted) doesn't re-trigger the "NOT writing to disk"
    # first-boot dialog.
    note_action "Running ephemerally from RAM (Ventoy / multiboot USB detected). Your data WILL NOT persist across reboots."
  fi
fi

# --- /media/wrolpi/config + Postgres data layout ------------------------
# Works regardless of whether /media/wrolpi is a bind (Live), a regular
# mount from /etc/fstab (Installed + external drive), or a plain
# directory on root (Installed without external drive).

if [ ! -d /media/wrolpi ]; then
  mkdir -p /media/wrolpi
fi
chown wrolpi:wrolpi /media/wrolpi 2>/dev/null || true

mkdir -p /media/wrolpi/config
chown wrolpi:wrolpi /media/wrolpi/config

# --- Postgres bind-mounts (live boots ONLY, idempotent) ------------------
# On live boots the root filesystem is an ephemeral overlay, so the
# cluster must live on the persistence partition: /var/lib/postgresql
# (data) and /etc/postgresql (config) are bind-mounted onto
# subdirectories of /media/wrolpi and travel with the stick.
#
# On INSTALLED systems Postgres stays at the normal Debian paths on the
# root filesystem.  The primary drive there may be NTFS/exFAT, which
# cannot host a Postgres data directory (no POSIX ownership/0700), and
# repair.sh chowns /media/wrolpi/config for the wrolpi user.

if [ "$MODE" != "installed" ]; then
  mkdir -p /media/wrolpi/config/postgresql/data \
           /media/wrolpi/config/postgresql/config
  chown postgres:postgres /media/wrolpi/config/postgresql \
                          /media/wrolpi/config/postgresql/data \
                          /media/wrolpi/config/postgresql/config
  chmod 0700 /media/wrolpi/config/postgresql/data

  bind_if_unmounted() {
    local src=$1 dest=$2
    mkdir -p "$dest"
    mountpoint -q "$dest" || mount --bind "$src" "$dest"
  }

  bind_if_unmounted /media/wrolpi/config/postgresql/data   /var/lib/postgresql
  bind_if_unmounted /media/wrolpi/config/postgresql/config /etc/postgresql
else
  # Installed system that previously ran with the binds (older bootstrap):
  # if a stale bind is still active from this boot, leave it alone — the
  # cluster logic below would otherwise misdetect.  It disappears on the
  # next reboot with this version.
  if mountpoint -q /var/lib/postgresql; then
    log "NOTE: /var/lib/postgresql is still bind-mounted (old layout); reboot to move Postgres to the root filesystem."
  fi
fi

# --- Postgres cluster ---------------------------------------------------
# Derive version from the installed Postgres binary so this stays correct
# if the package list is later bumped past postgresql-15.

PG_VERSION=$(ls /usr/lib/postgresql 2>/dev/null | sort -n | tail -1)
if [ -z "$PG_VERSION" ]; then
  log "ERROR: no postgresql server package found under /usr/lib/postgresql"
  exit 1
fi

if ! pg_lsclusters -h | awk '{print $1,$2}' | grep -q "^${PG_VERSION} main$"; then
  progress "Setting up Postgres cluster..."
  pg_createcluster "${PG_VERSION}" main
  note_action "Set up PostgreSQL ${PG_VERSION} cluster at /media/wrolpi/config/postgresql/"
fi
progress "Starting Postgres..."
systemctl start "postgresql@${PG_VERSION}-main.service"

# --- WROLPi DB schema + initial config import ---------------------------

if ! sudo -iu postgres psql -lqt | cut -d \| -f 1 | grep -qw wrolpi; then
  progress "Initializing WROLPi database (this can take a minute)..."
  /opt/wrolpi/scripts/initialize_api_db.sh
  note_action "Initialized the WROLPi database"
fi

# --- Certificates -------------------------------------------------------
# CA persists in /media/wrolpi/config/ssl/ (created on first run).  Leaf
# cert is regenerated every boot so SANs reflect the current hostname/IP.

progress "Generating TLS certificate..."
/opt/wrolpi/scripts/generate_certificates.sh

# --- Caddy: swap onboarding stub for the full Caddyfile if needed -------

if ! diff -q /opt/wrolpi/etc/raspberrypios/Caddyfile /etc/caddy/Caddyfile >/dev/null 2>&1; then
  progress "Configuring Caddy..."
  cp /opt/wrolpi/etc/raspberrypios/Caddyfile /etc/caddy/Caddyfile
  systemctl restart caddy || true
fi

# Signal to the Controller that the primary drive is set up.  Without this
# the Controller renders its onboarding wizard and offers the persistence
# partition as an unconfigured candidate.  Empty YAML yields defaults.
if [ ! -e /media/wrolpi/config/controller.yaml ]; then
  install -o wrolpi -g wrolpi -m 0644 /dev/null /media/wrolpi/config/controller.yaml
fi

# --- Enable and start the WROLPi runtime services -----------------------
# These units have implicit `After=wrolpi-bootstrap.service` (via our
# `Before=` in the unit file), so a blocking `systemctl --now` would
# deadlock: the runtime units won't start until bootstrap finishes, and
# bootstrap won't finish until systemctl returns.  Enable, then start
# with --no-block so systemd queues the starts after we exit.

progress "Starting WROLPi services..."
systemctl enable wrolpi-api.service wrolpi-app.service wrolpi-kiwix.service
systemctl start --no-block wrolpi-api.service wrolpi-app.service wrolpi-kiwix.service

# If we did anything notable, leave a summary for the XFCE autostart to
# show as a zenity dialog once the user lands on the desktop.
if [ -n "$SUMMARY" ]; then
  if [ "$MODE" = "loop" ]; then
    cat > "$SUMMARY_FILE" <<EOF
WROLPi is running, but NOT writing to disk.

$SUMMARY
You appear to have booted from Ventoy or a similar multiboot tool.
WROLPi can't safely write a persistence partition in that case, so
everything lives in RAM and will be lost when you reboot or power off.

To get a persistent install, flash the ISO directly to a USB drive
with dd or Raspberry Pi Imager and boot from that drive instead.
EOF
  else
    cat > "$SUMMARY_FILE" <<EOF
WROLPi finished setting itself up:

$SUMMARY
These persist between reboots:
  /media/wrolpi          — your library (videos, archives, zims, ...)
  /media/wrolpi/config   — configuration + Postgres data
EOF
  fi
  chmod 0644 "$SUMMARY_FILE"
fi

progress "WROLPi is ready."
log "bootstrap complete"
