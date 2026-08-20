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
  # Self-heal: ensure the unit is installed and current before starting it.
  # repair.sh installs it normally, but that runs late in the upgrade, so a
  # missing or stale unit would otherwise break delegation entirely.
  install -m644 /opt/wrolpi/etc/raspberrypios/wrolpi-upgrade.service \
    /etc/systemd/system/wrolpi-upgrade.service
  systemctl daemon-reload
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
    if [ "$RESTART_SERVICES_ON_FAILURE" = true ]; then
      echo "Restarting WROLPi services after failed upgrade..."
      systemctl start wrolpi-api || :
      systemctl start wrolpi-app || :
    fi
  fi
' EXIT

echo "Upgrading WROLPi from branch: ${BRANCH}"

set -x
set -e
set -o pipefail

# Units may not be installed yet if a previous install/repair failed; repair.sh installs them later.
systemctl stop wrolpi-api || :
systemctl stop wrolpi-app || :
RESTART_SERVICES_ON_FAILURE=true

# Restore the previously-running commit after a failed checkout or verification.
# Services must only restart on that known-good commit, so if the rollback does
# not land there, leave them stopped.
rollback_or_no_restart() {
  git -C /opt/wrolpi checkout -f -B "${BRANCH}" "${PREVIOUS_HEAD}" || :
  if [ "$(git -C /opt/wrolpi rev-parse HEAD 2>/dev/null)" != "${PREVIOUS_HEAD}" ]; then
    echo "ERROR: rollback to ${PREVIOUS_HEAD} failed; not restarting services."
    RESTART_SERVICES_ON_FAILURE=false
  fi
}

# Fetch the latest commits without modifying the working tree.
git -C /opt/wrolpi fetch || exit 4

# Import the trusted GPG key from the current (pre-upgrade) working tree into a temporary keyring.
GNUPGHOME=$(mktemp -d)
export GNUPGHOME
gpg --batch --quiet --import /opt/wrolpi/wrolpi/roland@learningselfreliance.com.gpg
# The throwaway keyring contains only the pinned WROLPi key, so mark it
# ultimately trusted: possession of the pinned key IS the trust anchor here,
# and this silences gpg's web-of-trust WARNING noise that makes healthy
# upgrade logs look scary.  Cosmetic only — verify-commit already ignores
# ownertrust when judging signature validity.
gpg --batch --list-keys --with-colons | awk -F: '/^fpr:/ {print $10":6:"; exit}' | \
  gpg --batch --quiet --import-ownertrust || :

# Verify the fetched commit is signed by the trusted key before checking it out.
if ! git -C /opt/wrolpi verify-commit origin/"${BRANCH}" 2>&1; then
  echo "ERROR: origin/${BRANCH} is not signed by the trusted WROLPi GPG key. Aborting upgrade."
  rm -rf "$GNUPGHOME"
  exit 5
fi

# Signature verified, safe to apply.
PREVIOUS_HEAD=$(git -C /opt/wrolpi rev-parse HEAD)
# Force the checkout so local working-tree changes (e.g. app/package-lock.json
# rewritten by npm install during a prior upgrade) cannot abort the switch.
# Use `checkout -B <branch> origin/<branch>` so the ref can never be mistaken for a path. A tracked `release/`
# directory otherwise collides with the `release` branch name, making a bare `git checkout release` ambiguous.
# checkout -B moves the ref before checking out the tree, so a failure here may
# leave a mixed tree; roll back before the EXIT trap restarts anything.
(cd /opt/wrolpi && git checkout -f -B "${BRANCH}" "origin/${BRANCH}") || {
  rollback_or_no_restart
  exit 4
}

# Verify HEAD again after checkout in case the branch was swapped between fetch and checkout.
if ! git -C /opt/wrolpi verify-commit HEAD 2>&1; then
  echo "ERROR: HEAD commit signature verification failed after checkout. Aborting upgrade."
  rollback_or_no_restart
  rm -rf "$GNUPGHOME"
  exit 6
fi

rm -rf "$GNUPGHOME"
unset GNUPGHOME

# From here scripts/upgrade.sh mutates the system; a blind restart could run
# half-upgraded code, so recovery belongs to repair.sh.
RESTART_SERVICES_ON_FAILURE=false

/opt/wrolpi/scripts/upgrade.sh 2>&1 | tee /opt/wrolpi/upgrade.log

set +x

echo "Upgrade end $(date '+%Y-%m-%d %H:%M:%S')" >>/opt/wrolpi/upgrade.log
