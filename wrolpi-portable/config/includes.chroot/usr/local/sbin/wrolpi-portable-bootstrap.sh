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
  # Compute next 1-MiB-aligned start sector after the last existing partition.
  LAST_END=$(sfdisk -d "$BOOT_DRIVE" | awk '/^\/dev\// {n=$4+$6} END{print n}')
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
cat > /mnt/persistence/persistence.conf <<EOF
/var/lib/postgresql union,source=postgresql-data
/etc/postgresql union,source=postgresql-config
/media/wrolpi union,source=wrolpi
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

if ! pg_lsclusters -h | awk '{print $1,$2}' | grep -q "^15 main$"; then
  progress "Setting up Postgres cluster..."
  pg_createcluster 15 main
fi
progress "Starting Postgres..."
systemctl start postgresql@15-main.service

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

# --- Enable and start the WROLPi runtime services -----------------------

progress "Starting WROLPi services..."
systemctl enable --now wrolpi-api.service wrolpi-app.service wrolpi-kiwix.service

progress "WROLPi Portable is ready."
log "bootstrap complete"
