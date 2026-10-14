#! /usr/bin/env bash
# This script will install WROLPi to `/opt/wrolpi` on a fresh/empty machine.  It is expected to be run once to
# install, and any subsequent runs will update WROLPi.  This script assumes it will be run as the `root` user.

Help() {
  # Display Help
  echo "Install WROLPi onto this machine."
  echo
  echo "Syntax: install.sh [-h] [-b BRANCH]"
  echo "options:"
  echo "h     Print this help."
  echo "b     Install from this git BRANCH."
  echo
}

BRANCH="release"
while getopts ":hb:" option; do
  case $option in
  h) # display Help
    Help
    exit
    ;;
  b)
    BRANCH="${OPTARG}"
    ;;
  *) # invalid argument(s)
    echo "Error: Invalid option"
    exit 1
    ;;
  esac
done

rpi=false
if (grep 'Raspberry Pi' /proc/cpuinfo >/dev/null); then
  rpi=true
fi

# Raspberry Pi OS and Debian both report the Debian release in VERSION_ID.  WROLPi requires Debian 13 (trixie) or
# newer; Debian 12 installs stay on their final version and cannot be upgraded in place.
os_id=""
os_version=""
if [ -r /etc/os-release ]; then
  os_id=$(awk -F= '$1=="ID"{gsub(/"/,"",$2);print $2}' /etc/os-release)
  os_version=$(awk -F= '$1=="VERSION_ID"{gsub(/"/,"",$2);print $2}' /etc/os-release)
fi
case "${os_version}" in
  '' | *[!0-9]*) os_version=0 ;;
esac
if [[ ${os_id} != "debian" || ${os_version} -lt 13 ]]; then
  echo 'This script can only be run on Debian 13 (trixie) or newer, or Raspberry Pi OS based on it!' && exit 2
fi

set -x
set -e

# Check that WROLPi directory exists, and contains wrolpi.
[ -d /opt/wrolpi ] && [ ! -d /opt/wrolpi/wrolpi ] && echo "/opt/wrolpi exists but does not contain wrolpi!" && exit 3

# Add the WROLPi directory as a global safe directory so root can fetch.
[ -d /opt/wrolpi ] && git config --global --add safe.directory /opt/wrolpi

# Get the latest WROLPi code.  Use the branch requested.
apt install -y git
git --version
git clone https://github.com/lrnselfreliance/wrolpi.git /opt/wrolpi || :
# Use `checkout -B <branch> origin/<branch>` so the ref can never be mistaken for a path. A tracked `release/`
# directory otherwise collides with the `release` branch name, making a bare `git checkout release` ambiguous.
(cd /opt/wrolpi && git fetch && git checkout -B "${BRANCH}" "origin/${BRANCH}" && git reset --hard origin/"${BRANCH}") || exit 4

if [ ${rpi} == true ]; then
  /opt/wrolpi/scripts/install_raspberrypios.sh 2>&1 | tee /opt/wrolpi/install.log
  install_code=${PIPESTATUS[0]}
else
  /opt/wrolpi/scripts/install_debian.sh 2>&1 | tee /opt/wrolpi/install.log
  install_code=${PIPESTATUS[0]}
fi

set +x

echo "Install end $(date '+%Y-%m-%d %H:%M:%S')" >>/opt/wrolpi/install.log

if [ "${install_code}" -ne 0 ]; then
  echo "Installation failed!"
fi

exit "${install_code}"
