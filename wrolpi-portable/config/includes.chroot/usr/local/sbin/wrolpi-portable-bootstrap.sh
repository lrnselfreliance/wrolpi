#!/usr/bin/env bash
# WROLPi Portable bootstrap — runs at every boot via
# wrolpi-portable-bootstrap.service. Idempotent throughout.
#
# First boot: the persistence partition does not yet exist.  This script
# creates it in the free space at the end of the boot drive, formats it as
# ext4 with label `persistence`, writes a persistence.conf so future boots
# pick it up automatically via live-boot, bind-mounts the source dirs over
# /var/lib/postgresql, /etc/postgresql, and /media/wrolpi, creates a fresh
# Postgres cluster, runs initialize_api_db.sh, and enables the WROLPi
# runtime services.
#
# Subsequent boots: live-boot's persistence machinery has already done the
# bind mounts (because the kernel cmdline includes `persistence
# persistence-label=persistence persistence-media=removable`).  Cluster and
# DB already exist.  Most steps no-op; we always regenerate the leaf TLS
# certificate to pick up the current hostname/IP, and we always ensure the
# wrolpi-* services are enabled and started.

set -euo pipefail

log() { echo "[wrolpi-portable-bootstrap] $*"; }

# Show progress on the Plymouth splash so the user sees what's happening
# during the 30-60s first-boot work.  Plymouth is up between initramfs and
# lightdm starting; we block lightdm via systemd ordering, so the splash
# owns the screen for our entire run.  Falls back to log-only if Plymouth
# isn't active (e.g. running this script manually over SSH).
progress() {
  plymouth display-message --text="$1" 2>/dev/null || true
  log "$1"
}

progress "Preparing WROLPi Portable..."

# --- Identify the boot drive ---------------------------------------------

# live-boot uses one of these mount points depending on version / config.
BOOT_PART=""
for mp in /usr/lib/live/mount/medium /run/live/medium /lib/live/mount/medium; do
  if BOOT_PART=$(findmnt -nr -o SOURCE "$mp" 2>/dev/null) && [ -n "$BOOT_PART" ]; then
    break
  fi
done
if [ -z "$BOOT_PART" ]; then
  log "ERROR: could not locate live medium mount point"
  exit 1
fi
BOOT_DRIVE=$(lsblk -no PKNAME "$BOOT_PART")
BOOT_DRIVE="/dev/${BOOT_DRIVE}"
log "live medium $BOOT_PART on $BOOT_DRIVE"

# --- Find or create persistence partition --------------------------------

PERSIST_PART=$(blkid -L persistence 2>/dev/null || true)
if [ -z "$PERSIST_PART" ]; then
  progress "Creating persistence partition on $BOOT_DRIVE..."
  # Compute next 1-MiB-aligned start sector after the highest-ending existing
  # partition.  We need MAX(start+size), not LAST: iso-hybrid layouts list a
  # small ESP (sdb2) AFTER the main data partition (sdb1) in sfdisk -d output
  # even though sdb1 ends much later on disk.  Parse via sed because sfdisk -d
  # pads values with spaces ("start=          64,") which breaks naive awk.
  LAST_END=$(sfdisk -d "$BOOT_DRIVE" \
    | sed -n 's|^/dev/[^ ]* *: *start= *\([0-9]\+\), *size= *\([0-9]\+\).*|\1 \2|p' \
    | awk '{e=$1+$2; if(e>m) m=e} END{print m+0}')
  if [ "${LAST_END:-0}" -lt 1 ]; then
    log "ERROR: failed to compute LAST_END from $BOOT_DRIVE partition table"
    exit 1
  fi
  START=$(( ((LAST_END + 2047) / 2048) * 2048 ))
  # --no-reread --force: required because the live medium is mounted from
  # this same drive.  Adding a new partition entry past the mounted one is
  # safe; we use partx -a below to inform the running kernel without forcing
  # a re-read of the whole partition table.
  echo "start=$START, type=83" | sfdisk --append --no-reread --force "$BOOT_DRIVE"
  partx -a "$BOOT_DRIVE" 2>/dev/null || true
  udevadm settle || true
  PERSIST_PART=$(blkid -L persistence 2>/dev/null || true)
  if [ -z "$PERSIST_PART" ]; then
    PERSIST_PART=$(lsblk -lnpo NAME "$BOOT_DRIVE" | tail -1)
  fi
  if ! [ -b "$PERSIST_PART" ]; then
    log "ERROR: failed to locate the newly created persistence partition"
    exit 1
  fi
  progress "Formatting $PERSIST_PART as ext4..."
  mkfs.ext4 -L persistence -F "$PERSIST_PART"
fi

# --- Mount persistence and prepare source-dir layout ---------------------

mkdir -p /mnt/persistence
mountpoint -q /mnt/persistence || mount "$PERSIST_PART" /mnt/persistence

mkdir -p /mnt/persistence/postgresql-data \
         /mnt/persistence/postgresql-config \
         /mnt/persistence/wrolpi

chown postgres:postgres /mnt/persistence/postgresql-data /mnt/persistence/postgresql-config
chmod 0700 /mnt/persistence/postgresql-data
chown wrolpi:wrolpi /mnt/persistence/wrolpi

# Write persistence.conf so live-boot's initramfs persistence machinery can
# apply these bind mounts before systemd starts on subsequent boots.
#
# `bind` (not `union`) is critical: `union` instructs live-boot to apply an
# OverlayFS union mount, which PostgreSQL explicitly does not support and
# which would silently corrupt data from the second boot onward.  On first
# boot bind_if_unmounted below does a real bind mount; on subsequent boots
# live-boot's initramfs reads this file and must do the same.
cat > /mnt/persistence/persistence.conf <<EOF
/var/lib/postgresql bind,source=postgresql-data
/etc/postgresql bind,source=postgresql-config
/media/wrolpi bind,source=wrolpi
EOF

# --- Bind mounts (idempotent — only mount if not already mounted) -------

bind_if_unmounted() {
  local src=$1 dest=$2
  mkdir -p "$dest"
  mountpoint -q "$dest" || mount --bind "$src" "$dest"
}

bind_if_unmounted /mnt/persistence/postgresql-data   /var/lib/postgresql
bind_if_unmounted /mnt/persistence/postgresql-config /etc/postgresql
bind_if_unmounted /mnt/persistence/wrolpi            /media/wrolpi

# --- Postgres cluster ----------------------------------------------------
# Derive version from the installed Postgres binary so this stays correct if
# the package list is later bumped past postgresql-15.  This matches what
# the chroot hook does when dropping the default cluster.

PG_VERSION=$(ls /usr/lib/postgresql 2>/dev/null | sort -n | tail -1)
if [ -z "$PG_VERSION" ]; then
  log "ERROR: no postgresql server package found under /usr/lib/postgresql"
  exit 1
fi

if ! pg_lsclusters -h | awk '{print $1,$2}' | grep -q "^${PG_VERSION} main$"; then
  progress "Setting up Postgres cluster..."
  pg_createcluster "${PG_VERSION}" main
fi
progress "Starting Postgres..."
systemctl start "postgresql@${PG_VERSION}-main.service"

# --- WROLPi DB schema + initial config import ----------------------------

if ! sudo -iu postgres psql -lqt | cut -d \| -f 1 | grep -qw wrolpi; then
  progress "Initializing WROLPi database (this can take a minute)..."
  /opt/wrolpi/scripts/initialize_api_db.sh
fi

# --- Certificates --------------------------------------------------------
# CA persists in /media/wrolpi/config/ssl/ (created on first run).  Leaf
# cert is regenerated every boot so SANs reflect the current hostname/IP.

progress "Generating TLS certificate..."
/opt/wrolpi/scripts/generate_certificates.sh

# --- Caddy: swap onboarding stub for the full Caddyfile if needed --------

if ! diff -q /opt/wrolpi/etc/raspberrypios/Caddyfile /etc/caddy/Caddyfile >/dev/null 2>&1; then
  progress "Configuring Caddy..."
  cp /opt/wrolpi/etc/raspberrypios/Caddyfile /etc/caddy/Caddyfile
  systemctl restart caddy || true
fi

# --- /media/wrolpi ownership + config dir --------------------------------

chown wrolpi:wrolpi /media/wrolpi 2>/dev/null || true
mkdir -p /media/wrolpi/config
chown wrolpi:wrolpi /media/wrolpi/config

# Signal to the Controller that the primary drive is set up.  The Controller
# treats /media/wrolpi/config/controller.yaml as the "drive is configured"
# sentinel (see controller.lib.config.is_primary_drive_mounted); without it
# the Controller renders its onboarding wizard and offers the persistence
# partition as an unconfigured candidate.  Empty YAML is valid and yields
# the defaults.
if [ ! -e /media/wrolpi/config/controller.yaml ]; then
  install -o wrolpi -g wrolpi -m 0644 /dev/null /media/wrolpi/config/controller.yaml
fi

# --- Enable and start the WROLPi runtime services -----------------------
# These units declare `After=wrolpi-portable-bootstrap.service` (via our
# Before= here in this unit), so a blocking `systemctl --now` would deadlock:
# the runtime units won't start until bootstrap finishes, and bootstrap won't
# finish until systemctl returns.  Enable, then start with --no-block so
# systemd queues the starts after we exit.

progress "Starting WROLPi services..."
systemctl enable wrolpi-api.service wrolpi-app.service wrolpi-kiwix.service
systemctl start --no-block wrolpi-api.service wrolpi-app.service wrolpi-kiwix.service

progress "WROLPi Portable is ready."
log "bootstrap complete"
