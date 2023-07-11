#!/usr/bin/env bash

MEDIA_DIRECTORY=/media/wrolpi

# Source environment file after declaring globals.
[ -f /opt/wrolpi/.env ] && source /opt/wrolpi/.env

echo "This script is running as $(whoami)"

function check_directory() {
  directory=$1
  good_message=$2
  bad_message=$3
  if [ -d "${directory}" ]; then
    echo "OK: ${good_message}"
  else
    echo "FAILED: ${bad_message}"
  fi
}

function check_file() {
  file=$1
  good_message=$2
  bad_message=$3
  if [ -f "${file}" ]; then
    echo "OK: ${good_message}"
  else
    echo "FAILED: ${bad_message}"
  fi
}

echo

rpi=false
debian11=false
if (grep 'Raspberry Pi' /proc/cpuinfo >/dev/null); then
  rpi=true
fi
if (grep 'PRETTY_NAME="Debian GNU/Linux 11 (bullseye)"' /etc/os-release >/dev/null); then
  debian11=true
fi

if [[ ${rpi} == true ]]; then
  echo 'OK: Running on Raspberry Pi'
elif [[ ${debian11} == true ]]; then
  echo 'OK: Running on Debian 11'
else
  echo "FAILED: Running on unknown operating system"
fi

if id -u wrolpi >/dev/null 2>&1; then
  echo "OK: Found wrolpi user"
else
  echo "FAILED: No wrolpi user found"
fi

check_directory /opt/wrolpi "The WROLPi directory exists" "The WROLPi directory does not exist at /opt/wrolpi"
check_directory /opt/wrolpi-blobs "The WROLPi blobs directory exists" "The WROLPi blobs directory does not exist at /opt/wrolpi-blobs"
check_file /opt/wrolpi/main.py "The WROLPi main script exists" "The WROLPi main script does not exist at /opt/wrolpi/main.py"
check_file ${MEDIA_DIRECTORY}/config/wrolpi.yaml "The WROLPi config file exists" "The WROLPi config file does not exist"

echo
# Postgresql

systemctl status postgresql.service >/dev/null &&
  echo "OK: Postgres found" ||
  echo "FAILED: Postgres service does not exist"

if netstat -ant | grep LISTEN | grep 127.0.0.1:5432 >/dev/null; then
  echo "OK: Port 5432 is occupied"
else
  echo "FAILED: Port 5432 is not occupied"
fi

[ -S /var/run/postgresql/.s.PGSQL.5432 ] &&
  echo "OK: Postgres is using file socket" ||
  echo "FAILED: Postgres is not using file socket"

psql -l >/dev/null 2>/dev/null &&
  echo "OK: Connected to postgres" ||
  echo "FAILED: Unable to connect to postgres"

if psql -l 2>/dev/null | grep wrolpi >/dev/null; then
  echo "OK: Found wrolpi database"

  if psql wrolpi -c '\d' | grep "file_group" >/dev/null; then
    echo "OK: WROLPi database is initialized"

    if [ "$(psql wrolpi -c 'copy (select count(*) from file_group) to stdout')" -gt 0 ]; then
      echo "OK: WROLPi database has files"
    else
      echo "FAILED: WROLPi database has no files"
    fi
  else
    echo "FAILED: WROLPi is not initialized"
  fi
else
  echo "FAILED: Unable to find wrolpi database"
fi

echo
# API

if [ -f /opt/wrolpi/venv/bin/python3 ]; then
  echo "OK: WROLPi Python virtual environment exists"

  if /opt/wrolpi/venv/bin/python3 /opt/wrolpi/main.py -h >/dev/null; then
    echo 'OK: WROLPi main can be run'
  else
    echo "Failed: WROLPi main could not be run"
  fi

else
  echo "FAILED: WROLPi Python virtual environment does not exist"
fi

if systemctl list-unit-files "*wrolpi-api*" >/dev/null; then
  echo "OK: WROLPi API systemd exists"
else
  echo "FAILED: WROLPi API systemd does not exist"
fi

if [ -f /etc/systemd/system/wrolpi-api.service ]; then
  if systemctl status wrolpi-api.service >/dev/null; then
    echo "OK: WROLPi API service is up"
  else
    echo "FAILED: WROLPi API service is not up"
  fi
fi

if curl -s http://0.0.0.0:8081/api/echo | grep -i '"method":"GET"' >/dev/null; then
  echo "OK: WROLPi API echoed correctly"
else
  echo "FAILED: WROLPi API did not echo correctly"
fi

echo
# Webapp

if [ -d /opt/wrolpi/app ]; then
  echo "OK: WROLPi app directory exists"

  if (cd /opt/wrolpi/app && npm ls >/dev/null); then
    echo "OK: WROLPi app exists"
  else
    echo "FAILED: WROLPi app does not exist"
  fi
else
  echo "FAILED: WROLPi app directory does not exist"
fi

if systemctl list-unit-files "*wrolpi-app*" >/dev/null; then
  echo "OK: WROLPi app systemd exists"
else
  echo "FAILED: WROLPi app systemd does not exist"
fi

if [ -f /etc/systemd/system/wrolpi-app.service ]; then
  if systemctl status wrolpi-app.service >/dev/null; then
    echo "OK: WROLPi app service is up"
  else
    echo "FAILED: WROLPi app service is not up"
  fi
fi

if curl -s http://0.0.0.0:5000 | grep -i wrolpi >/dev/null; then
  echo "OK: WROLPi app responded with interface"
else
  echo "FAILED: WROLPi app did not respond with interface"
fi

if netstat -ant | grep LISTEN | grep 127.0.0.1:80 >/dev/null; then
  echo "OK: Port 80 is occupied"
else
  echo "FAILED: Port 80 is not occupied"
fi

if systemctl list-unit-files "*nginx*" >/dev/null; then
  echo "OK: nginx systemd exists"
else
  echo "FAILED: nginx does not exist"
fi

echo
# Map

if psql -l 2>/dev/null | grep gis >/dev/null; then
  echo "OK: Found map database"

  if psql gis -c '\d' | grep water_polygons >/dev/null; then
    echo "OK: Map database is initialized"
  else
    echo "FAILED: Map database is not initialized"
  fi
else
  echo "FAILED: Unable to find map database"
fi

if systemctl list-unit-files "*renderd*" >/dev/null; then
  echo "OK: renderd systemd exists"
else
  echo "FAILED: renderd systemd does not exist"
fi

if curl -s http://0.0.0.0:8084 2>/dev/null | grep -i openstreetmap >/dev/null; then
  echo "OK: Map app responded"
else
  echo "FAILED: Map app did not respond"
fi

check_file /opt/wrolpi-blobs/gis-map.dump.gz "Map initialization blob exists" "Map initialization blob does not exist"

check_file /var/www/html/leaflet.js "Leaflet.js exists" "Leaflet.js does not exist"

echo
# Kiwix

check_file /media/wrolpi/zims/library.xml "The kiwix library file exists" "The kiwix library file does not exist at /media/wrolpi/zims/library.xml"
if curl -s http://0.0.0.0:8085 2>/dev/null | grep -i kiwix >/dev/null; then
  echo "OK: Kiwix app responded"
else
  echo "FAILED: Kiwix app did not respond"
fi

echo
# Media Directory

check_directory "${MEDIA_DIRECTORY}" "The media directory exists" "The media directory does not exist at ${MEDIA_DIRECTORY}"
if [ -d "${MEDIA_DIRECTORY}" ] && [ -d ${MEDIA_DIRECTORY}/config ]; then
  if touch ${MEDIA_DIRECTORY}/config; then
    echo "OK: Can modify media directory"
  else
    echo "FAILED: Cannot modify media directory"
  fi
fi

if curl -s http://0.0.0.0/media/ | grep "Index of" >/dev/null; then
  echo "OK: Media directory files are served by nginx"
  if curl -s -I http://0.0.0.0/media/config/wrolpi.yaml | grep '200 OK' >/dev/null; then
    echo "OK: Config can be fetched from nginx"
  else
    echo "FAILED: Media directory files are not being served"
  fi
else
  echo "FAILED: Media directory files are not being served"
fi

echo
# 3rd party commands
if single-file -h >/dev/null 2>&1; then
  echo "OK: Singlefile can be run"
else
  echo "FAILED: Singlefile cannot be run"
fi

check_file /usr/bin/readability-extractor "Readability exists" "Readability does not exist"

if wget -h >/dev/null 2>&1; then
  echo "OK: wget can be run"
else
  echo "FAILED: wget cannot be run"
fi

if /opt/wrolpi/venv/bin/yt-dlp -h >/dev/null 2>&1; then
  echo "OK: yt-dlp can be run"
else
  echo "FAILED: yt-dlp cannot be run"
fi

if chromium-browser -h >/dev/null 2>&1; then
  echo "OK: Chromium can be run"
else
  echo "FAILED: Chromium cannot be run"
fi

if ffmpeg -h >/dev/null 2>&1; then
  echo "OK: ffmpeg can be run"
else
  echo "FAILED: ffmpeg cannot be run"
fi
