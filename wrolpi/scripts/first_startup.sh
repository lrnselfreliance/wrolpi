#!/usr/bin/env bash
# This script is run once on the first startup of a Raspberry Pi.

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
