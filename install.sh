#! /usr/bin/env bash
# This script will install WROLPi to `/opt/wrolpi` on a fresh/empty Raspberry Pi.  It is expected to be run once to
# install, and any subsequent runs will update WROLPi.  This script assumes it will be run as the `root` user.

Help() {
  # Display Help
  echo "Install WROLPi onto this Raspberry Pi."
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
debian11=false
if (grep 'Raspberry Pi' /proc/cpuinfo >/dev/null); then
  rpi=true
fi
if (grep 'PRETTY_NAME="Debian GNU/Linux 11 (bullseye)"' /etc/os-release >/dev/null); then
  debian11=true
fi

if [[ ${rpi} == false && ${debian11} == false ]]; then
  echo 'This script can only be run on a Raspberry Pi or Debian 11!' && exit 2
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
(cd /opt/wrolpi && git fetch && git checkout "${BRANCH}" && git reset --hard origin/"${BRANCH}") || exit 4

if [ ${rpi} == true ]; then
  /opt/wrolpi/scripts/install_ubuntu_20.04.sh 2>&1 | tee /opt/wrolpi/install.log
  install_code=${PIPESTATUS[0]}
elif [ ${debian11} == true ]; then
  /opt/wrolpi/scripts/install_debian_11.sh 2>&1 | tee /opt/wrolpi/install.log
  install_code=${PIPESTATUS[0]}
fi

set +x

echo "Install end $(date '+%Y-%m-%d %H:%M:%S')" >>/opt/wrolpi/install.log
exit "${install_code}"
