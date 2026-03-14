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

# If not running via the wrolpi-upgrade service, delegate to it so logs are captured.
if [ -z "$WROLPI_UPGRADE_SERVICE" ]; then
  trap 'echo ""; echo "Note: The upgrade service is still running in the background."; echo "Monitor with: journalctl -fu wrolpi-upgrade.service"' INT
  echo "Delegating upgrade to wrolpi-upgrade.service..."
  # Write branch config for the service.
  echo "BRANCH=${BRANCH}" >/tmp/wrolpi-upgrade.env
  chown wrolpi:wrolpi /tmp/wrolpi-upgrade.env
  # Start following journal in background (new entries only).
  journalctl -fn0 -u wrolpi-upgrade.service &
  JOURNAL_PID=$!
  # Start service (blocks until complete for oneshot).
  systemctl start wrolpi-upgrade.service
  EXIT_CODE=$?
  # Clean up journal follower.
  kill $JOURNAL_PID 2>/dev/null
  wait $JOURNAL_PID 2>/dev/null
  exit $EXIT_CODE
fi

# Clean up and report status on exit.
trap '
  EXIT_STATUS=$?
  rm -f /tmp/wrolpi-upgrade.env
  # Clean up temporary GPG keyring if it exists.
  if [ -n "$GNUPGHOME" ] && [ -d "$GNUPGHOME" ]; then
    rm -rf "$GNUPGHOME"
  fi
  if [ $EXIT_STATUS -eq 0 ]; then
    echo "WROLPi upgrade has completed"
  else
    echo "WROLPi upgrade has FAILED (exit code: $EXIT_STATUS)"
  fi
' EXIT

echo "Upgrading WROLPi from branch: ${BRANCH}"

set -x
set -e
set -o pipefail

systemctl stop wrolpi-api
systemctl stop wrolpi-app

# Fetch the latest commits without modifying the working tree.
git -C /opt/wrolpi fetch || exit 4

# Import the trusted GPG key from the current (pre-upgrade) working tree into a temporary keyring.
GNUPGHOME=$(mktemp -d)
export GNUPGHOME
gpg --batch --quiet --import /opt/wrolpi/wrolpi/roland@learningselfreliance.com.gpg

# Verify the fetched commit is signed by the trusted key before checking it out.
if ! git -C /opt/wrolpi verify-commit origin/"${BRANCH}" 2>&1; then
  echo "ERROR: origin/${BRANCH} is not signed by the trusted WROLPi GPG key. Aborting upgrade."
  rm -rf "$GNUPGHOME"
  exit 5
fi

# Signature verified, safe to apply.
(cd /opt/wrolpi && git checkout "${BRANCH}" && git reset --hard origin/"${BRANCH}") || exit 4

# Verify HEAD again after checkout in case the branch was swapped between fetch and checkout.
if ! git -C /opt/wrolpi verify-commit HEAD 2>&1; then
  echo "ERROR: HEAD commit signature verification failed after checkout. Aborting upgrade."
  rm -rf "$GNUPGHOME"
  exit 6
fi

rm -rf "$GNUPGHOME"
unset GNUPGHOME

/opt/wrolpi/scripts/upgrade.sh 2>&1 | tee /opt/wrolpi/upgrade.log

set +x

echo "Upgrade end $(date '+%Y-%m-%d %H:%M:%S')" >>/opt/wrolpi/upgrade.log
