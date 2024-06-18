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

# Do not run this script again.
systemctl disable wrolpi-first-startup.service
