#!/usr/bin/env bash
# Usage: install_python_requirements.sh PIP REQUIREMENTS_TXT
#
# Installs REQUIREMENTS_TXT's generated lock (the .lock beside it, see scripts/lock_requirements.sh) with
# --require-hashes, so every package is checked against a hash committed with WROLPi instead of trusting PyPI over TLS.
# Wheels only: building a source archive would install its build tools (setuptools) without hashes.
#
# Then upgrades the yt-dlp lines of REQUIREMENTS_TXT without hashes: yt-dlp is left out of the lock so devices get
# YouTube fixes as soon as they are released.  --no-deps keeps that unhashed download to yt-dlp's own distributions; its
# dependencies come only from the lock, so a yt-dlp that needs newer ones waits for the lock to be regenerated.
set -e

PIP=$1
REQUIREMENTS=$2
LOCK="${REQUIREMENTS%.txt}.lock"

# Retried: image builds and fresh installs can hit a flaky network.
retry() {
  local attempt
  for attempt in 1 2 3; do
    "$@" && return 0
  done
  return 1
}

retry "${PIP}" install --require-hashes --only-binary :all: -r "${LOCK}"

yt_dlp=()
while IFS= read -r line; do
  yt_dlp+=("${line}")
done < <(grep -E '^yt-dlp' "${REQUIREMENTS}" | sed 's/[[:space:]]*#.*//')
if [ ${#yt_dlp[@]} -gt 0 ]; then
  retry "${PIP}" install --upgrade --no-deps --only-binary :all: "${yt_dlp[@]}"
fi
