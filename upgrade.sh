#! /usr/bin/env bash
# This script will upgrade the WROLPi API and App.  It is required that you install WROLPi first.

Help() {
  # Display Help
  echo "Upgrade WROLPi API and App on this machine."
  echo
  echo "Syntax: upgrade.sh [-h] [-b BRANCH]"
  echo "options:"
  echo "h     Print this help."
  echo "b     Upgrade from this git BRANCH (default: current branch, or 'release')."
  echo
}

BRANCH=""
BRANCH_OVERRIDE=false
while getopts ":hb:" option; do
  case $option in
  h) # display Help
    Help
    exit
    ;;
  b)
    BRANCH="${OPTARG}"
    BRANCH_OVERRIDE=true
    ;;
  *) # invalid argument(s)
    echo "Error: Invalid option"
    exit 1
    ;;
  esac
done

if [ ! -d /opt/wrolpi ] || [ ! -d /opt/wrolpi/wrolpi ]; then
  echo "You must install WROLPi first.  Try: /opt/wrolpi/install.sh"
  exit 2
fi

# Re-execute this script if it wasn't called with sudo.
if [ $EUID != 0 ]; then
  sudo "$0" "$@"
  exit $?
fi

# Determine which branch to use for upgrade.
if [ "$BRANCH_OVERRIDE" = false ]; then
  CURRENT_BRANCH=$(git -C /opt/wrolpi branch --show-current 2>/dev/null)
  if [ -n "$CURRENT_BRANCH" ]; then
    BRANCH="$CURRENT_BRANCH"
  else
    BRANCH="release"
  fi
fi

echo "Upgrading WROLPi from branch: ${BRANCH}"

set -x
set -e

systemctl stop wrolpi-api
systemctl stop wrolpi-app

# Pull the latest commit of the requested branch.
(cd /opt/wrolpi && git fetch && git checkout "${BRANCH}" && git reset --hard origin/"${BRANCH}") || exit 4

/opt/wrolpi/scripts/upgrade.sh 2>&1 | tee /opt/wrolpi/upgrade.log

set +x

echo "Upgrade end $(date '+%Y-%m-%d %H:%M:%S')" >>/opt/wrolpi/upgrade.log

echo "WROLPi upgrade has completed"
