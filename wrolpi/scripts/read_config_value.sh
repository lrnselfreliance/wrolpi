#! /usr/bin/env bash
# Read a single top-level scalar value from WROLPi's config (wrolpi.yaml).
#
# wrolpi.yaml is the source of truth for configuration, but scripts that run
# outside the Python API (e.g. start_kiwix_serve.sh, or a minimal Docker
# container) still need to read config values.  This reader has zero
# dependencies -- no Python, no jq/yq -- so it runs identically everywhere.
#
# Usage: read_config_value.sh KEY [DEFAULT]
#   Prints the value of the top-level scalar KEY, or DEFAULT (empty if omitted)
#   when the config file or the key is missing/empty.
#
# Limitation: only top-level scalar keys are supported (sufficient for the
# *_destination keys).  Nested keys, lists, and multi-line values are not
# parsed.  wrolpi.yaml is written by PyYAML and is regular, so this is reliable
# for the keys it is used with.
set -u

KEY="${1:?Usage: read_config_value.sh KEY [DEFAULT]}"
DEFAULT="${2:-}"

MEDIA_DIRECTORY="${MEDIA_DIRECTORY:-/media/wrolpi}"
CONFIG="${MEDIA_DIRECTORY}/config/wrolpi.yaml"

value=""
if [ -f "${CONFIG}" ]; then
  value=$(awk -v key="${KEY}" '
    # Only consider unindented (top-level) "key:" lines.
    /^[A-Za-z0-9_]+[[:space:]]*:/ {
      idx = index($0, ":")
      k = substr($0, 1, idx - 1)
      gsub(/[[:space:]]+$/, "", k)
      if (k == key) {
        v = substr($0, idx + 1)
        sub(/^[[:space:]]+/, "", v)        # leading whitespace
        sub(/[[:space:]]+#.*$/, "", v)     # trailing inline comment
        sub(/[[:space:]]+$/, "", v)        # trailing whitespace
        # Strip a matching pair of surrounding quotes.
        if (v ~ /^".*"$/ || v ~ /^'\''.*'\''$/)
          v = substr(v, 2, length(v) - 2)
        print v
        exit
      }
    }
  ' "${CONFIG}")
fi

if [ -z "${value}" ]; then
  printf '%s\n' "${DEFAULT}"
else
  printf '%s\n' "${value}"
fi
