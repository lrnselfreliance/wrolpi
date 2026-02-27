#!/usr/bin/env bash
# This script is run once on the first startup of a Raspberry Pi or Debian Live.

set -x

# Generate nginx certificate for HTTPS if it doesn't exist.
/opt/wrolpi/scripts/generate_certificates.sh

# Ensure nginx config files are in place (safeguard in case build didn't complete this).
if [ ! -f /etc/nginx/conf.d/wrolpi.conf ]; then
    echo "wrolpi.conf missing, copying from /opt/wrolpi..."
    cp /opt/wrolpi/etc/raspberrypios/wrolpi.conf /etc/nginx/conf.d/wrolpi.conf
fi
# Remove default site if it exists (WROLPi nginx.conf doesn't use sites-enabled).
rm -f /etc/nginx/sites-enabled/default

# Enable and start nginx now that certificates exist.
systemctl enable nginx
systemctl start nginx || echo "Warning: nginx failed to start"

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
