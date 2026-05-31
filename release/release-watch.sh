#!/bin/bash
# Poll GitHub for a newly-published WROLPi release and build it.
#
# This is the *outbound* poller that replaces an inbound webhook: GitHub never
# connects to this machine.  Once an hour (via the systemd timer) we ask the
# public GitHub API for the newest release, compare its version to whatever is
# already published in latest.json on the CDN, and if they differ we run
# release.sh to build and publish it.  latest.json is the source of truth for
# "already built" -- there is no local bookkeeping for success.
#
# A local state file records a tag that failed to build.  Builds are expensive
# (hours), so by default a failed tag is attempted once and then NOT auto-retried
# -- the notify hook alerts you, and you investigate and clear the marker (or run
# release.sh manually) instead of burning hours on blind retries.
#
#   ./release-watch.sh        # check once and act
#
# Honors $S3CFG (passed through to release.sh) and these optional env vars:
#   STATE_DIR   where to keep the lock + failure marker (default /var/lib/wrolpi-release)
#   MAX_RETRIES build attempts before giving up on a tag (default 1 = no auto-retry)

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

REPO="lrnselfreliance/wrolpi"
# Read the manifest for the dedup from the Spaces ORIGIN, not the CDN.  The CDN
# caches latest.json (~5 min), so a watcher run firing right after a release
# publishes can still read the previous tag and trigger a redundant rebuild.
# The origin is strongly consistent, so it always reflects the latest publish.
MANIFEST_URL="https://wrolpi.nyc3.digitaloceanspaces.com/latest.json"
STATE_DIR="${STATE_DIR:-/var/lib/wrolpi-release}"
MAX_RETRIES="${MAX_RETRIES:-1}"

LOCK="${STATE_DIR}/build.lock"
FAIL_STATE="${STATE_DIR}/failed-tag"

mkdir -p "${STATE_DIR}"

log() { echo "[release-watch] $*"; }

# Newest non-draft release tag.  GitHub's /releases list is ordered by creation
# date, so [0] is the most recently *published* release -- exactly the trigger
# we want.  Prereleases (-beta) are intentionally included (every WROLPi release
# is a prerelease), so we deliberately do NOT filter on `.prerelease`.  Read-only
# and unauthenticated; the 60 req/hr public limit is irrelevant at hourly cadence.
LATEST_TAG=$(curl -fsSL -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${REPO}/releases" \
  | jq -r '[.[] | select(.draft == false)][0].tag_name // empty')
[ -n "${LATEST_TAG}" ] || { log "No releases found; nothing to do."; exit 0; }

# What is already built?  release.sh records the git ref it built in the
# manifest's `.tag`.  Compare that directly against the release tag: it is an
# exact match and immune to any divergence between a tag name and the
# version.txt content it carries.  (Comparing versions could loop forever -- a
# build that succeeds but whose .version never equals the tag would rebuild
# every hour.)  A missing manifest (404) means "nothing built yet".
PUBLISHED_TAG=$(curl -fsSL "${MANIFEST_URL}" 2>/dev/null \
  | jq -r '.tag // empty' || true)

if [ "${PUBLISHED_TAG}" = "${LATEST_TAG}" ]; then
  log "Up to date (published ${LATEST_TAG}); nothing to do."
  exit 0
fi

log "New release ${LATEST_TAG} (published: ${PUBLISHED_TAG:-none})."

# Skip a tag that has already failed MAX_RETRIES times -- needs a human.
if [ -f "${FAIL_STATE}" ]; then
  read -r failed_tag failed_count < "${FAIL_STATE}" || true
  if [ "${failed_tag}" = "${LATEST_TAG}" ] && [ "${failed_count:-0}" -ge "${MAX_RETRIES}" ]; then
    log "ERROR: ${LATEST_TAG} has failed ${failed_count} times; not auto-retrying."
    log "Investigate, then run release.sh manually or remove ${FAIL_STATE}."
    exit 1
  fi
fi

# Only one build at a time.  If the timer fires mid-build, just exit.
exec 9>"${LOCK}"
if ! flock -n 9; then
  log "A build is already running; skipping this check."
  exit 0
fi

log "Building ${LATEST_TAG}..."
if "${SCRIPT_DIR}/release.sh" -b "${LATEST_TAG}"; then
  log "Published ${LATEST_TAG}."
  rm -f "${FAIL_STATE}"
else
  rc=$?
  count=1
  if [ -f "${FAIL_STATE}" ]; then
    read -r ft fc < "${FAIL_STATE}" || true
    [ "${ft}" = "${LATEST_TAG}" ] && count=$(( ${fc:-0} + 1 ))
  fi
  echo "${LATEST_TAG} ${count}" > "${FAIL_STATE}"
  log "ERROR: build of ${LATEST_TAG} failed (attempt ${count}, exit ${rc})."
  exit "${rc}"
fi
