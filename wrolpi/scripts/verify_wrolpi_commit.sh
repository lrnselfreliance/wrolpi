#!/usr/bin/env bash
# Usage: verify_wrolpi_commit.sh REPO REV [KEY_FILE]
#
# Exits non-zero unless REV in the git checkout REPO is signed by the WROLPi release key.  KEY_FILE defaults to the
# key committed beside this script; the image builds pass the key from the build checkout, never from the clone being
# verified.

# The key is imported into a throwaway keyring, and the signature must come from the pinned fingerprint, so a key file
# swapped along with the code is rejected.  install.sh carries an identical copy of this function because it runs
# before any verified checkout exists; a test keeps the two the same.
verify_wrolpi_commit() {
  local repo=$1 rev=$2 key=$3
  local fingerprint=${WROLPI_SIGNING_FINGERPRINT:-A74A9634A86C65F3C13949AD1BA620CE6C9A4680}
  local gnupghome status rc=1
  # A short path: gpg's agent socket lives in GNUPGHOME and its path is limited to ~108 characters.
  gnupghome=$(mktemp -d /tmp/wgpg.XXXXXX) || return 1
  if GNUPGHOME="${gnupghome}" gpg --batch --quiet --import "${key}" 2>/dev/null; then
    # VALIDSIG <signing key fingerprint> ... <primary key fingerprint>
    status=$(GNUPGHOME="${gnupghome}" git -C "${repo}" verify-commit --raw "${rev}" 2>&1) &&
      awk -v fpr="${fingerprint}" '$2 == "VALIDSIG" && ($3 == fpr || $NF == fpr) {found = 1} END {exit !found}' \
        <<<"${status}" && rc=0
  fi
  rm -rf "${gnupghome}"
  [ ${rc} -eq 0 ] || echo "ERROR: ${rev} in ${repo} is not signed by the WROLPi key ${fingerprint}" >&2
  return ${rc}
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  verify_wrolpi_commit "$1" "$2" "${3:-$(dirname "$(realpath "$0")")/../roland@learningselfreliance.com.gpg}"
fi
