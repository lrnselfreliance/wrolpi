#! /usr/bin/env bash

# Update systemd files.
cp /opt/wrolpi/etc/raspberrypios/wrolpi-api.service /etc/systemd/system/
/usr/bin/systemctl daemon-reload

# Upgrade the API and App.
/bin/bash /opt/wrolpi/scripts/build_api_and_app.sh

# Update nginx configs
cp /opt/wrolpi/nginx.conf /etc/nginx/nginx.conf
cp /opt/wrolpi/50x.html /var/www/50x.html
/usr/sbin/nginx -s reload
