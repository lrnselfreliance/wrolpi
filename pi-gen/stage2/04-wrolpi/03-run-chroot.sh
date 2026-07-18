#! /usr/bin/env bash
set -e
set -x

# Generate and set default locale to avoid perl warnings.
# Users can change this later via: sudo raspi-config -> Localisation Options
# or: sudo dpkg-reconfigure locales
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8
export LANG=en_US.UTF-8

# Use Network Manager for Hotspot.
apt purge -y hostapd
apt autoremove -y

cat >>/etc/profile <<'EOF'
alias ll='ls -lh'
alias la='ll -a'
EOF

# Create WROLPi user.  This user will own the media directory, API, and App.
useradd -md /home/wrolpi wrolpi -s "$(command -v bash)"

# Install Node console commands.
npm i -g serve@12.0.1 single-file-cli@2.0.73 readability-extractor@0.0.6

# Install Deno runtime.
DENO_VERSION="v2.8.3"
curl -fsSL "https://github.com/denoland/deno/releases/download/${DENO_VERSION}/deno-aarch64-unknown-linux-gnu.zip" -o /tmp/deno.zip
unzip /tmp/deno.zip -d /usr/local/bin/
chmod +x /usr/local/bin/deno
rm /tmp/deno.zip
deno --version

# Put the latest WROLPi in /opt/wrolpi.
git clone -b "${WROLPI_BRANCH:-release}" https://github.com/lrnselfreliance/wrolpi.git /opt/wrolpi
# `git config --global` needs HOME, which is empty when the build runs under
# systemd (the release poller service has no HOME); set it to root's home.
export HOME=/root
git config --global --add safe.directory /opt/wrolpi

# Install the map toolchain (pmtiles CLI + tippecanoe).  Shared with the Debian
# Live build and on-device upgrades so versions/pins live in one place.  Baking
# it in keeps a fresh Pi from compiling tippecanoe on first boot -- a slow,
# CPU-heavy step on weak hardware.
/opt/wrolpi/wrolpi/scripts/install_map_tools.sh

# Install Python requirements.  Try multiple times because pypi may stop responding.
python3 -m venv /opt/wrolpi/venv
/opt/wrolpi/venv/bin/pip3 install -r /opt/wrolpi/requirements.txt ||
  /opt/wrolpi/venv/bin/pip3 install -r /opt/wrolpi/requirements.txt ||
  /opt/wrolpi/venv/bin/pip3 install -r /opt/wrolpi/requirements.txt

# Install Controller with separate venv.
echo "Pre-installing WROLPi Controller..."
python3 -m venv /opt/wrolpi/controller/venv
/opt/wrolpi/controller/venv/bin/pip install --upgrade pip
/opt/wrolpi/controller/venv/bin/pip install -r /opt/wrolpi/controller/requirements.txt ||
  /opt/wrolpi/controller/venv/bin/pip install -r /opt/wrolpi/controller/requirements.txt ||
  /opt/wrolpi/controller/venv/bin/pip install -r /opt/wrolpi/controller/requirements.txt
echo "Controller pre-installed"

# Install webapp.
(cd /opt/wrolpi/app && npm install)

# `npm install` rewrites the tracked app/package-lock.json.  build_app.sh (below)
# stamps build/.build-stamp from that working tree, but on-device repair.sh runs
# `git reset --hard` before it stamps -- reverting the lock -- so a stamp baked
# against the dirty lock can never match on first boot and the Pi rebuilds the app
# (the exact OOM-prone step this bake-in avoids).  Reset to HEAD here, exactly as
# repair.sh does, so the baked stamp represents committed source.  Only the lock is
# reverted; build/, node_modules, and the venvs are untracked and survive.
git -C /opt/wrolpi reset --hard HEAD

# Build the React production bundle now, so it is baked into the image.  Without
# this the Pi would build on first boot -- a multi-minute, memory-hungry step
# that can OOM on a 2GB Pi.  build_app.sh stamps the output so the on-device
# repair.sh sees it as current and never rebuilds.
/opt/wrolpi/scripts/build_app.sh

chown -R wrolpi:wrolpi /opt/wrolpi

# Install Caddy from official apt repo.
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y caddy

# Configure Caddy.
mkdir -p /etc/caddy
cp /opt/wrolpi/etc/raspberrypios/Caddyfile /etc/caddy/Caddyfile
mkdir -p /var/www
cp /opt/wrolpi/etc/raspberrypios/50x.html /var/www/50x.html

# WROLPi needs a few privileged commands.
cp /opt/wrolpi/etc/raspberrypios/90-wrolpi /etc/sudoers.d/90-wrolpi
chmod 0440 /etc/sudoers.d/90-wrolpi
# Verify this new file is valid.
visudo -c -f /etc/sudoers.d/90-wrolpi

mkdir /media/wrolpi
chown wrolpi:wrolpi /media/wrolpi

cp /opt/wrolpi/etc/raspberrypios/wrolpi-*.service /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi-*.timer /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi.target /etc/systemd/system/
# Enable first startup script.
systemctl enable wrolpi-first-startup.service
# Enable Controller service to start on boot.
systemctl enable wrolpi-controller.service
# Enable weekly certificate renewal check.
systemctl enable wrolpi-cert-renew.timer

# Copy MOTD scripts, delete original.
cp /opt/wrolpi/etc/raspberrypios/motd/20-wrolpi.motd /etc/update-motd.d/20-wrolpi
cp /opt/wrolpi/etc/raspberrypios/motd/30-wrolpi-first.motd /etc/update-motd.d/30-wrolpi
chmod +x /etc/update-motd.d/*
truncate -s 0 /etc/motd

# NetworkManager for the hotspot.
systemctl enable NetworkManager

# Enable iperf3 for speed testing.
systemctl enable iperf3

set +x

echo
echo "======================================================================"
echo "03-run-chroot.sh completed"
echo "======================================================================"
echo
