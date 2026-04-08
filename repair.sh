#!/usr/bin/env bash
# This script will attempt to repair a WROLPi installation.  It will not use internet.

cd /opt/wrolpi || (echo "Cannot repair.  /opt/wrolpi does not exist" && exit 1)

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

rpi=false
if (grep 'Raspberry Pi' /proc/cpuinfo >/dev/null); then
  rpi=true
fi

set -e
set -x

# Stop services if they are running.
systemctl stop wrolpi-controller.service || :
systemctl stop wrolpi-api.service || :
systemctl stop wrolpi-app.service || :
systemctl stop wrolpi-kiwix.service || :
systemctl stop caddy || :

# Clear Python bytecode cache from virtual environments to fix potential corruption.
echo "Clearing Python bytecode cache..."
find /opt/wrolpi/venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || :
find /opt/wrolpi/venv -name "*.pyc" -delete 2>/dev/null || :
find /opt/wrolpi/controller/venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || :
find /opt/wrolpi/controller/venv -name "*.pyc" -delete 2>/dev/null || :
find /opt/wrolpi-help/venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || :
find /opt/wrolpi-help/venv -name "*.pyc" -delete 2>/dev/null || :

# Create the WROLPi user
grep wrolpi: /etc/passwd || useradd -md /home/wrolpi wrolpi -s "$(command -v bash)"
[ -f /home/wrolpi/.pgpass ] || cat >/home/wrolpi/.pgpass <<'EOF'
127.0.0.1:5432:wrolpi:wrolpi:wrolpi
EOF
chmod 0600 /home/wrolpi/.pgpass

# Reset any inadvertent changes to the WROLPi repo.  Restore ownership in case this repair script fails.
git config --global --add safe.directory /opt/wrolpi
git reset HEAD --hard
chown -R wrolpi:wrolpi /opt/wrolpi

# Copy configs to system.
mkdir -p /etc/caddy
cp /opt/wrolpi/etc/raspberrypios/Caddyfile /etc/caddy/Caddyfile
mkdir -p /var/www
cp /opt/wrolpi/etc/raspberrypios/50x.html /var/www/50x.html

# Generate certificate for HTTPS.
/opt/wrolpi/scripts/generate_certificates.sh

# Install map fonts from blob (needed for MapLibre map labels).
MAP_FONTS_BLOB=/opt/wrolpi-blobs/map-fonts.tar.gz
if [ -f "${MAP_FONTS_BLOB}" ]; then
  mkdir -p /opt/wrolpi/modules/map/static/fonts
  tar -xzf "${MAP_FONTS_BLOB}" -C /opt/wrolpi/modules/map/static/
fi

# Start Caddy quickly so user can access Controller from React UI
systemctl start caddy || :

# WROLPi needs a few privileged commands.
cp /opt/wrolpi/etc/raspberrypios/90-wrolpi /etc/sudoers.d/90-wrolpi
chmod 0440 /etc/sudoers.d/90-wrolpi
# Verify this new file is valid.
visudo -c -f /etc/sudoers.d/90-wrolpi

# Install the systemd services
cp /opt/wrolpi/etc/raspberrypios/wrolpi*.service /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi-*.timer /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi.target /etc/systemd/system/
systemctl enable wrolpi-controller.service
systemctl enable wrolpi-api.service
systemctl enable wrolpi-app.service
systemctl enable wrolpi-kiwix.service
systemctl enable wrolpi-help.service
systemctl enable wrolpi-cert-renew.timer

# Repair Controller (offline-safe - no pip install)
repair_controller() {
    echo "Checking WROLPi Controller..."

    # Check venv exists
    if [ ! -f /opt/wrolpi/controller/venv/bin/python ]; then
        echo "ERROR: Controller venv missing!"
        echo "Run install.sh or upgrade.sh (requires internet) to reinstall."
        return 1
    fi

    # Check venv is functional
    if ! /opt/wrolpi/controller/venv/bin/python --version > /dev/null 2>&1; then
        echo "ERROR: Controller venv is corrupted!"
        echo "Run install.sh or upgrade.sh (requires internet) to reinstall."
        return 1
    fi

    # Check systemd service is installed
    if [ ! -f /etc/systemd/system/wrolpi-controller.service ]; then
        echo "Controller systemd service not installed, copying..."
        cp /opt/wrolpi/etc/raspberrypios/wrolpi-controller.service /etc/systemd/system/
        systemctl daemon-reload
    fi

    # Ensure service is enabled
    if ! systemctl is-enabled wrolpi-controller > /dev/null 2>&1; then
        echo "Enabling Controller service..."
        systemctl enable wrolpi-controller
    fi

    echo "Controller repair completed"
}

# Run Controller repair if venv exists (skip on fresh install)
if [ -d /opt/wrolpi/controller/venv ]; then
    repair_controller || echo "Controller repair failed, continuing..."
fi

# Start Controller so user can monitor repair in UI.
systemctl start wrolpi-controller

/usr/bin/systemctl daemon-reload

# WROLPi needs a few privileged commands.
cp /opt/wrolpi/etc/raspberrypios/90-wrolpi /etc/sudoers.d/90-wrolpi
chmod 0440 /etc/sudoers.d/90-wrolpi
# Verify this new file is valid.
visudo -c -f /etc/sudoers.d/90-wrolpi

# Configure Postgresql.  Do this after the API is stopped.
/opt/wrolpi/scripts/initialize_api_db.sh
# wrolpi user is superuser so they can import maps.
sudo -iu postgres psql -c "alter user wrolpi with superuser"

# Create the media directory.  This should be mounted by the maintainer.
[ -d /media/wrolpi ] || mkdir /media/wrolpi
# Create config directory if external drive is mounted, and is empty.
if grep -qs /media/wrolpi /proc/mounts && [ -z "$(ls -A /media/wrolpi)" ] && [ ! -d /media/wrolpi/config ]; then
  mkdir /media/wrolpi/config
fi

# Build the frontend app.
(cd /opt/wrolpi/app && npm run build)

# Change owner of the media directory, ignore any errors because the drive may be fat/exfat/etc.
chown wrolpi:wrolpi /media/wrolpi 2>/dev/null || echo "Ignoring failure to change media directory permissions."
# Ensure the config directory is owned by wrolpi so the API can write config files.
[ -d /media/wrolpi/config ] && chown -R wrolpi:wrolpi /media/wrolpi/config 2>/dev/null || :

# Remove immutable flag from blob files before chown (may not exist or may not be set).
chattr -i /opt/wrolpi-blobs/* 2>/dev/null || :

chown -R wrolpi:wrolpi /home/wrolpi /opt/wrolpi*

# Protect blob files from accidental modification or deletion.
# These files are critical for initializing WROLPi.
if [ -d /opt/wrolpi-blobs ] && ls /opt/wrolpi-blobs/* >/dev/null 2>&1; then
  chown -R root:root /opt/wrolpi-blobs
  chmod 444 /opt/wrolpi-blobs/*
  chattr +i /opt/wrolpi-blobs/*
fi

# Copy MOTD once the repair has been successful.
cp /opt/wrolpi/etc/raspberrypios/motd/30-wrolpi.motd /etc/update-motd.d/30-wrolpi
chmod +x /etc/update-motd.d/*

# Copy desktop shortcuts to existing users (new users get them from /etc/skel).
if [[ ${rpi} == true ]]; then
  for user_home in /home/wrolpi /home/pi; do
    if [ -d "${user_home}/Desktop" ]; then
      cp /opt/wrolpi/etc/raspberrypios/*.desktop "${user_home}/Desktop/"
      chown -R "$(basename ${user_home})":"$(basename ${user_home})" "${user_home}/Desktop/"
    fi
  done
  # Update skeleton for future users.
  mkdir -p /etc/skel/Desktop
  cp /opt/wrolpi/etc/raspberrypios/*.desktop /etc/skel/Desktop/
fi

systemctl restart wrolpi-help
systemctl start wrolpi.target

set +x

echo "Repair has completed.  You may run /opt/wrolpi/help.sh to check system status."
