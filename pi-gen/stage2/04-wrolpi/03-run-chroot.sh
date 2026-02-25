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

# Change postgresql "main" cluster port to 5432.
sed -i 's/port =.*/port = 5432/' /etc/postgresql/15/main/postgresql.conf

# Install Node console commands.
npm i -g serve@12.0.1 single-file-cli@2.0.73 readability-extractor@0.0.6 carto@1.2.0

# Install Deno runtime.
DENO_VERSION="v2.2.4"
curl -fsSL "https://github.com/denoland/deno/releases/download/${DENO_VERSION}/deno-aarch64-unknown-linux-gnu.zip" -o /tmp/deno.zip
unzip /tmp/deno.zip -d /usr/local/bin/
chmod +x /usr/local/bin/deno
rm /tmp/deno.zip
deno --version

# Put the latest WROLPi in /opt/wrolpi.
git clone -b "${WROLPI_BRANCH:-release}" https://github.com/lrnselfreliance/wrolpi.git /opt/wrolpi
git config --global --add safe.directory /opt/wrolpi

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
(cd /opt/wrolpi/app && npm install && npm run build)

chown -R wrolpi:wrolpi /opt/wrolpi

# Configure nginx.
cp /opt/wrolpi/etc/raspberrypios/nginx.conf /etc/nginx/nginx.conf
cp /opt/wrolpi/etc/raspberrypios/50x.html /var/www/50x.html
# Copy wrolpi.conf which defines the location blocks for reverse proxy.
[ -f /etc/nginx/conf.d/default.conf ] && rm /etc/nginx/conf.d/default.conf
cp /opt/wrolpi/etc/raspberrypios/wrolpi.conf /etc/nginx/conf.d/wrolpi.conf

# WROLPi needs a few privileged commands.
cp /opt/wrolpi/etc/raspberrypios/90-wrolpi /etc/sudoers.d/90-wrolpi
chmod 0440 /etc/sudoers.d/90-wrolpi
# Verify this new file is valid.
visudo -c -f /etc/sudoers.d/90-wrolpi

mkdir /media/wrolpi
chown wrolpi:wrolpi /media/wrolpi

cp /opt/wrolpi/etc/raspberrypios/wrolpi-*.service /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi.target /etc/systemd/system/
# Enable first startup script.
systemctl enable wrolpi-first-startup.service
# Enable Controller service to start on boot.
systemctl enable wrolpi-controller.service

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
