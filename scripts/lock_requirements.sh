#!/usr/bin/env bash
# Regenerates the hash-locked .lock beside each requirements.txt.  Run it after editing a requirements.txt (or merging
# a dependabot bump); wrolpi/test/test_python_requirements.py fails until the lock satisfies its requirements.txt.
#
# The locks are universal: they carry the hashes for every platform's wheels (Raspberry Pi and amd64), for the Python
# each environment runs.  Wheels only: building a source archive installs its build tools (setuptools) without hashes,
# so a package with no wheel fails here.  yt-dlp is left out; scripts/install_python_requirements.sh upgrades it.
set -e

cd "$(dirname "$(dirname "$(realpath "$0")")")"

lock() {
  local requirements=$1 python=$2
  shift 2
  uv pip compile "${requirements}" --universal --python-version "${python}" --generate-hashes --only-binary :all: \
    --no-header --quiet "$@" -o "${requirements%.txt}.lock"
}

lock requirements.txt 3.13 --no-emit-package yt-dlp --no-emit-package yt-dlp-ejs
lock controller/requirements.txt 3.13
# browserless/chrome is Ubuntu 22.04.
lock docker/archive/requirements.txt 3.10
