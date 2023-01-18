#! /usr/bin/env bash
set -e
set -x

cat >> /etc/profile << 'EOF'
alias ll='ls -lh'
alias la='ll -a'
EOF

# Install Node console commands.
single-file --version || npm i -g serve@12.0.1 single-file-cli@1.0.15 'git+https://github.com/lrnselfreliance/readability-extractor' carto@1.2.0

# Put the latest WROLPi release in /opt/wrolpi.
rm -rf /opt/wrolpi
git clone -b master https://github.com/lrnselfreliance/wrolpi.git /opt/wrolpi
chown -R ${FIRST_USER_NAME}:${FIRST_USER_NAME} /opt/wrolpi

# Install Python requirements.
pip3 install --upgrade pip
pip3 install -r /opt/wrolpi/requirements.txt

# Install webapp.
cd /opt/wrolpi/app
npm install
npm run build

# Configure nginx.
cp /opt/wrolpi/nginx.conf /etc/nginx/nginx.conf
cp /opt/wrolpi/50x.html /var/www/50x.html

# WROLPi needs a few privileged commands.
cat >/etc/sudoers.d/90-wrolpi <<'EOF'
%wrolpi ALL=(ALL) NOPASSWD:/usr/bin/nmcli,/usr/bin/cpufreq-set
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl restart renderd.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl stop renderd.service
%wrolpi ALL= NOPASSWD:/usr/bin/systemctl start renderd.service
EOF
chmod 660 /etc/sudoers.d/90-wrolpi

[ -d /media/wrolpi ] || mkdir /media/wrolpi
chown ${FIRST_USER_NAME}:${FIRST_USER_NAME} /media/wrolpi

cp /opt/wrolpi/etc/ubuntu20.04/wrolpi-api.service /etc/systemd/system/
cp /opt/wrolpi/etc/ubuntu20.04/wrolpi-app.service /etc/systemd/system/
cp /opt/wrolpi/etc/ubuntu20.04/wrolpi.target /etc/systemd/system/

systemctl enable wrolpi-api.service
systemctl enable wrolpi-app.service

