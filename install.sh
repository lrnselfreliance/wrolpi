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

if (! grep 'Raspberry Pi' /proc/cpuinfo >/dev/null); then
  echo 'This script can only be run on a Raspberry Pi!' && exit 2
fi

set -x
set -e

# Check that WROLPi directory exists, and contains wrolpi.
[ -d /opt/wrolpi ] && [ ! -d /opt/wrolpi/wrolpi ] && echo "/opt/wrolpi exists but does not contain wrolpi!" && exit 3

# Get the latest WROLPi code.  Use the branch requested.
apt install -y git
git --version
git clone https://github.com/lrnselfreliance/wrolpi.git /opt/wrolpi || :
(cd /opt/wrolpi && git fetch && git checkout "${BRANCH}" && git reset --hard origin/"${BRANCH}") || exit 4

/opt/wrolpi/scripts/ubuntu_20.04_install.sh 2>&1 | tee /opt/wrolpi/install.log
exit $?
