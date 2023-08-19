#! /usr/bin/env bash
set -e
set -x

# Use Network Manager for Hotspot.
apt purge -y hostapd
apt autoremove -y

cat >>/etc/profile <<'EOF'
alias ll='ls -lh'
alias la='ll -a'
EOF

# Create WROLPi user.  This user will own the media directory, API, and App.
# The `pi` user will be the maintainer's user.
grep wrolpi: /etc/passwd || useradd -md /home/wrolpi wrolpi -s "$(command -v bash)"
usermod -aG pi wrolpi

# Change default postgresql port to 5432.
sed -i 's/port = 5433/port = 5432/' /etc/postgresql/13/main/postgresql.conf

# Install Node console commands.
single-file --version || npm i -g serve@12.0.1 single-file-cli@1.0.15 readability-extractor@0.0.6 carto@1.2.0

# Put the latest WROLPi master in /opt/wrolpi.
rm -rf /opt/wrolpi
git clone -b master https://github.com/lrnselfreliance/wrolpi.git /opt/wrolpi
git config --global --add safe.directory /opt/wrolpi

# Install Python requirements.
pip3 install --upgrade pip
python3 -m venv /opt/wrolpi/venv
/opt/wrolpi/venv/bin/pip3 install -r /opt/wrolpi/requirements.txt

# Install webapp.
cd /opt/wrolpi/app
npm install
npm run build

# Add wrolpi database password to pi user
cat >/home/pi/.pgpass <<'EOF'
127.0.0.1:5432:gis:_renderd:wrolpi
127.0.0.1:5432:wrolpi:wrolpi:wrolpi
EOF
chown -R pi:pi /home/pi
chmod 0600 /home/pi/.pgpass

chown -R wrolpi:wrolpi /opt/wrolpi

# Configure nginx.
cp /opt/wrolpi/nginx.conf /etc/nginx/nginx.conf
cp /opt/wrolpi/50x.html /var/www/50x.html

# WROLPi needs a few privileged commands.
cat >/etc/sudoers.d/90-wrolpi <<'EOF'
%wrolpi ALL=(ALL) NOPASSWD:/usr/bin/nmcli,/usr/bin/cpufreq-set
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl restart renderd.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl stop renderd.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl start renderd.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl restart wrolpi-kiwix.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl stop wrolpi-kiwix.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl start wrolpi-kiwix.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl restart wrolpi-api.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl stop wrolpi-api.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl start wrolpi-api.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl restart wrolpi-app.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl stop wrolpi-app.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl start wrolpi-app.service
%wrolpi ALL= NOPASSWD:/opt/wrolpi/scripts/import_map.sh
%wrolpi ALL= NOPASSWD:/usr/sbin/shutdown
EOF
chmod 0440 /etc/sudoers.d/90-wrolpi

[ -d /media/wrolpi ] || mkdir /media/wrolpi
chown wrolpi:wrolpi /media/wrolpi

cp /opt/wrolpi/etc/raspberrypios/wrolpi-api.service /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi-app.service /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi-kiwix.service /etc/systemd/system/
cp /opt/wrolpi/etc/raspberrypios/wrolpi.target /etc/systemd/system/

systemctl enable wrolpi-api.service
systemctl enable wrolpi-app.service
systemctl enable wrolpi-kiwix.service

# NetworkManager for the hotspot.
systemctl enable NetworkManager

set +x

echo
echo "======================================================================"
echo "03-run-chroot.sh completed"
echo "======================================================================"
echo
