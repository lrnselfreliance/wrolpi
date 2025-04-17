#!/usr/bin/env bash

MEDIA_DIRECTORY=/media/wrolpi

# Source environment file after declaring globals.
[ -f /opt/wrolpi/.env ] && source /opt/wrolpi/.env

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

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

echo "WROLPi version: $(cat /opt/wrolpi/wrolpi/version.txt)"

echo

rpi=false
rpi4=false
rpi5=false
debian12=false
grep -q 'Raspberry Pi' /proc/cpuinfo >/dev/null && rpi=true
grep -q 'Raspberry Pi 4' /proc/cpuinfo >/dev/null && rpi4=true
grep -q 'Raspberry Pi 5' /proc/cpuinfo >/dev/null && rpi5=true
grep -q 'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"' /etc/os-release >/dev/null && debian12=true

if [[ ${rpi4} == true ]]; then
  echo 'OK: Running on Raspberry Pi 4'
elif [[ ${rpi5} == true ]]; then
  echo 'OK: Running on Raspberry Pi 5'
elif [[ ${rpi} == true ]]; then
  echo 'OK: Running on unknown Raspberry Pi'
elif [[ ${debian12} == true ]]; then
  echo 'OK: Running on Debian 12'
else
  echo "FAILED: Running on unknown operating system"
fi

if dmesg | grep -q 'Undervoltage detected' >/dev/null 2>&1; then
  echo 'FAILED: Under voltage detected!  Use a more powerful power supply.'
fi
if dmesg | grep -q 'over-current change' >/dev/null 2>&1; then
  echo 'FAILED: Over current detected!  Your peripherals are using too much power!'
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

if sudo -i -u wrolpi psql -l 2>/dev/null | grep wrolpi >/dev/null; then
  echo "OK: Found wrolpi database"

  if sudo -i -u wrolpi psql wrolpi -c '\d' | grep "file_group" >/dev/null; then
    echo "OK: WROLPi database is initialized"

    if [ "$(sudo -i -u wrolpi psql wrolpi -c 'copy (select count(*) from file_group) to stdout' 2>/dev/null)" -gt 0 ]; then
      echo "OK: WROLPi database has files"
    else
      echo "FAILED: WROLPi database has no files.  You need to refresh your files: https://$(hostname).local/files"
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

  if /opt/wrolpi/venv/bin/python3 /opt/wrolpi/main.py -h 2>/dev/null > /dev/null; then
    echo 'OK: WROLPi main can be run'
  else
    echo "Failed: WROLPi main could not be run"
  fi

  if /opt/wrolpi/venv/bin/sanic --help 2>/dev/null > /dev/null; then
    echo 'OK: Sanic can be run'
  else
    echo "Failed: Sanic could not be run"
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

if curl -s http://0.0.0.0:8081/api/echo --max-time 5 | grep -i '"method":"GET"' >/dev/null; then
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

if curl -s http://0.0.0.0:3000 --max-time 5 | grep -i wrolpi >/dev/null; then
  echo "OK: WROLPi app responded with UI"
else
  echo "FAILED: WROLPi app did not respond with UI"
fi

if curl -s http://0.0.0.0:3000/epub/epub.html --max-time 5 | grep -i epub.js >/dev/null; then
  echo "OK: WROLPi app responded with ebook interface"
else
  echo "FAILED: WROLPi app did not respond with ebook interface"
fi

if netstat -ant | grep LISTEN | grep 0.0.0.0:80 >/dev/null; then
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

if netstat -ant | grep LISTEN | grep 127.0.0.1:5433 >/dev/null; then
  echo "OK: Port 5433 is occupied"
else
  echo "FAILED: Port 5433 is not occupied"
fi

if sudo -iu postgres psql --port=5433 -l 2>/dev/null | grep gis >/dev/null; then
  echo "OK: Found map database"

  if sudo -iu postgres psql --port=5433 gis -c '\d' | grep water_polygons >/dev/null; then
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

if curl -k -s https://0.0.0.0:8084 --max-time 5 2>/dev/null | grep -i openstreetmap >/dev/null; then
  echo "OK: Map app responded"
else
  echo "FAILED: Map app did not respond"
fi

check_file /opt/wrolpi-blobs/map-db-gis.dump "Map initialization blob exists" "Map initialization blob does not exist"

check_file /var/www/html/leaflet.js "Leaflet.js exists" "Leaflet.js does not exist"

echo
# Kiwix

check_file /media/wrolpi/zims/library.xml "The kiwix library file exists" "The kiwix library file does not exist at /media/wrolpi/zims/library.xml"
if curl -k -s https://0.0.0.0:8085 --max-time 5 2>/dev/null | grep -i kiwix >/dev/null; then
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
if grep -qs "${MEDIA_DIRECTORY}" /proc/mounts >/dev/null 2>&1 ; then
  echo "OK: Media directory is a mounted drive"
else
  echo "FAILED: Media directory is not a mounted drive.  (This is fine if you don't have an external drive.)"
fi

if curl -k -s https://0.0.0.0/media/ --max-time 5 | grep "Index of /media/" >/dev/null; then
  echo "OK: Media directory files are served by nginx"
  if curl -k -s -I https://0.0.0.0/media/config/wrolpi.yaml --max-time 5 | grep '200 OK' >/dev/null; then
    echo "OK: Config can be fetched from nginx"
  else
    echo "FAILED: Media directory files are not being served"
  fi
else
  echo "FAILED: Media directory files are not being served"
fi

if curl -k -s https://0.0.0.0/download/ --max-time 5 | grep "Index of /download/" >/dev/null; then
  echo "OK: Media download directory files are served by nginx"
  if curl -k -s -I https://0.0.0.0/download/config/wrolpi.yaml --max-time 5 | grep '200 OK' >/dev/null; then
    echo "OK: Config can be downloaded from nginx"
  else
    echo "FAILED: Media download directory files are not being served"
  fi
else
  echo "FAILED: Media download directory files are not being served"
fi

if [ "$(stat -c '%U' /media/wrolpi/)" == 'wrolpi' ]; then
  echo "OK: Media directory is owned by wrolpi user"
else
  echo "FAILED: Media directory is not owned by wrolpi user"
fi

echo
# 3rd party commands
if single-file -h >/dev/null 2>&1; then
  echo "OK: Singlefile can be run"
else
  echo "FAILED: Singlefile cannot be run"
fi

if [ -f /usr/bin/readability-extractor ]; then
  echo "OK: readability exists"
else
  if [ -f /usr/local/bin/readability-extractor ]; then
    echo "OK: readability exists"
  else
    echo "FAILED: readability does not exist"
  fi
fi

if wget -h >/dev/null 2>&1; then
  echo "OK: wget can be run"
else
  echo "FAILED: wget cannot be run"
fi

if aria2c -h >/dev/null 2>&1; then
  echo "OK: aria2c can be run"
else
  echo "FAILED: aria2c cannot be run"
fi

if /opt/wrolpi/venv/bin/yt-dlp -h >/dev/null 2>&1; then
  echo "OK: yt-dlp can be run"
else
  echo "FAILED: yt-dlp cannot be run"
fi

if chromium-browser -h >/dev/null 2>&1; then
  echo "OK: Chromium can be run"
else
  if chromium -h >/dev/null 2>&1; then
    echo "OK: Chromium can be run"
  else
    echo "FAILED: Chromium cannot be run"
  fi
fi

if ffmpeg -h >/dev/null 2>&1; then
  echo "OK: ffmpeg can be run"
else
  echo "FAILED: ffmpeg cannot be run"
fi

echo
# Help Service
if /opt/wrolpi-help/venv/bin/mkdocs --help &>/dev/null; then
  echo "OK: Help mkdocs can be run"
else
  echo "FAILED: Help mkdocs cannot be run"
fi

if curl -k -s https://0.0.0.0:8086/ --max-time 5 | grep MkDocs 2>/dev/null >/dev/null; then
  echo "OK: Help service is running"
else
  echo "FAILED: Help service is not running"
fi

echo
# Internet
if ping -c1 1.1.1.1 -W 5 &>/dev/null; then
  echo "OK: Can ping 1.1.1.1"
else
  echo "FAILED: Cannot ping 1.1.1.1.  Is internet working?"
fi

if ping -c1 one.one.one.one -W 5 &>/dev/null; then
  echo "OK: Can ping one.one.one.one"
else
  echo "FAILED: Cannot ping one.one.one.one  Is internet working?"
fi
