#! /usr/bin/env bash
# Configure WROLPi on Raspberry Pi OS.
set -e
set -x

# All users can access the wrolpi database.
cat >/etc/skel/.pgpass <<'EOF'
127.0.0.1:5432:wrolpi:wrolpi:wrolpi
EOF
chmod 0600 /etc/skel/.pgpass
cat >/etc/skel/.gitconfig  <<'EOF'
[safe]
	directory = /opt/wrolpi
	directory = /opt/wrolpi-help
EOF
# Copy desktop shortcuts.
mkdir /etc/skel/Desktop
cp /opt/wrolpi/etc/raspberrypios/*desktop /etc/skel/Desktop

# Verify blob files were copied in by 02-run.sh (downloaded by build.sh).
[[ -f /opt/wrolpi-blobs/map-fonts.tar.gz && -s /opt/wrolpi-blobs/map-fonts.tar.gz ]] || \
  (echo "ERROR: map-fonts.tar.gz missing from /opt/wrolpi-blobs!" && exit 1)
[[ -f /opt/wrolpi-blobs/map-overview.pmtiles && -s /opt/wrolpi-blobs/map-overview.pmtiles ]] || \
  (echo "ERROR: map-overview.pmtiles missing from /opt/wrolpi-blobs!" && exit 1)

# Install WROLPi Help.
/opt/wrolpi/scripts/install_help_service.sh

# Create the media directory for the wrolpi user.
mkdir -p /media/wrolpi
chown -R wrolpi:wrolpi /media/wrolpi /home/wrolpi /opt/wrolpi*

# Protect blob files from accidental modification or deletion.
if [ -d /opt/wrolpi-blobs ] && ls /opt/wrolpi-blobs/* >/dev/null 2>&1; then
  chown -R root:root /opt/wrolpi-blobs
  chmod 444 /opt/wrolpi-blobs/*
  chattr +i /opt/wrolpi-blobs/*
fi

set +x

echo
echo "======================================================================"
echo "04-run-chroot.sh completed"
echo "======================================================================"
echo
