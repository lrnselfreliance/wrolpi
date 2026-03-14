#!/usr/bin/env bash
# This script is run once on the first startup of a Raspberry Pi or Debian Live.

set -x

# Generate certificate for HTTPS — only if primary drive is mounted.
# If not mounted, onboarding + repair will generate certs after drive setup.
if mountpoint -q /media/wrolpi; then
  /opt/wrolpi/scripts/generate_certificates.sh
else
  echo "Primary drive not mounted, skipping certificate generation (onboarding will handle this)"
fi

# Copy landing page for HTTP certificate download.
cp /opt/wrolpi/etc/raspberrypios/landing.html /var/www/landing.html

# Ensure Caddy config is in place (safeguard in case build didn't complete this).
if [ ! -f /etc/caddy/Caddyfile ]; then
    echo "Caddyfile missing, copying from /opt/wrolpi..."
    mkdir -p /etc/caddy
    cp /opt/wrolpi/etc/raspberrypios/Caddyfile /etc/caddy/Caddyfile
fi

# Enable and start Caddy now that certificates exist.
systemctl enable caddy
systemctl start caddy || echo "Warning: caddy failed to start"

# Copy skeleton files to first users home directory.
USER_HOME=$(getent passwd 1000 | cut -d: -f6)
if [ "$(ls -A /etc/skel)" ]; then
    echo "Files found in /etc/skel, copying to $USER_HOME..."
    # Copy files from /etc/skel to the user's home directory
    cp -r /etc/skel/. "$USER_HOME"
    # Change ownership to the user with UID 1000
    chown -R 1000:1000 "$USER_HOME"
    echo "Files copied successfully."
else
    echo "No files found in /etc/skel."
    exit 1
fi

# Add the user created on startup to the wrolpi group.
USER_NAME=$(getent passwd 1000 | cut -d: -f1)
grep wrolpi: /etc/passwd || useradd -md /home/wrolpi wrolpi -s "$(command -v bash)"
usermod -aG wrolpi ${USER_NAME}
usermod -aG sudo ${USER_NAME}

# Do not run this script again.
systemctl disable wrolpi-first-startup.service
