#!/usr/bin/env bash
# Usage: install_python_requirements.sh PIP REQUIREMENTS_TXT
#
# Installs REQUIREMENTS_TXT's generated lock (the .lock beside it, see scripts/lock_requirements.sh) with
# --require-hashes, so every package is checked against a hash committed with WROLPi instead of trusting PyPI over TLS.
# Then upgrades the yt-dlp lines of REQUIREMENTS_TXT without hashes: yt-dlp is left out of the lock so devices get
# YouTube fixes as soon as they are released.  Its dependencies are in the lock and only change if it needs newer ones.
set -e

PIP=$1
REQUIREMENTS=$2
LOCK="${REQUIREMENTS%.txt}.lock"

# Retried: image builds and fresh installs can hit a flaky network.
for attempt in 1 2 3; do
  "${PIP}" install --require-hashes -r "${LOCK}" && break
  [ ${attempt} -lt 3 ] || exit 1
done

mapfile -t yt_dlp < <(grep -E '^yt-dlp' "${REQUIREMENTS}" | sed 's/[[:space:]]*#.*//')
if [ ${#yt_dlp[@]} -gt 0 ]; then
  "${PIP}" install --upgrade --upgrade-strategy only-if-needed "${yt_dlp[@]}"
fi
