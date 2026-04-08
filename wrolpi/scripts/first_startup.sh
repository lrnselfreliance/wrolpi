#!/usr/bin/env bash
# This script is run once on the first startup of a Raspberry Pi or Debian Live.

set -x

mkdir -p /etc/caddy /etc/ssl/wrolpi

if [ -f /media/wrolpi/config/ssl/ca.crt ]; then
    # Persistent CA exists (drive mounted with previous install).
    # Generate a fresh leaf cert from the existing CA and use the full Caddyfile.
    echo "Persistent CA found, generating leaf cert and using full Caddyfile"
    /opt/wrolpi/scripts/generate_certificates.sh
    cp /opt/wrolpi/etc/raspberrypios/Caddyfile /etc/caddy/Caddyfile
else
    # No persistent CA (fresh install, no drive, or empty drive).
    # Generate a throwaway self-signed cert directly into /etc/ssl/wrolpi/
    # so Caddy can listen on :443. Never writes to /media/wrolpi/.
    echo "No persistent CA, generating temporary cert for onboarding"
    openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout /etc/ssl/wrolpi/cert.key \
        -out /etc/ssl/wrolpi/cert.crt \
        -days 1 -subj "/CN=wrolpi-onboarding"
    chmod 640 /etc/ssl/wrolpi/cert.key /etc/ssl/wrolpi/cert.crt
    if id caddy >/dev/null 2>&1; then
        chown root:caddy /etc/ssl/wrolpi/cert.key /etc/ssl/wrolpi/cert.crt
    fi
    cp /opt/wrolpi/etc/raspberrypios/Caddyfile.onboarding /etc/caddy/Caddyfile
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
