#! /usr/bin/env bash
# This file imports all *.zim files in the Zim media directory, then starts kiwix-serve.
set -u

# The media directory and project directory are overridable for testing;
# they default to the production locations.
MEDIA_DIRECTORY="${MEDIA_DIRECTORY:-/media/wrolpi}"
PROJECT_DIR="${PROJECT_DIR:-/opt/wrolpi}"
# Default Zim shipped in /opt/wrolpi-blobs; served when no real zim is available.
DEFAULT_ZIM="${DEFAULT_ZIM:-/opt/wrolpi-blobs/default.zim}"

[ ! -d "${MEDIA_DIRECTORY}" ] && echo "Cannot start kiwix without media directory mounted" && exit 1

# Honor the configured Zim directory (wrolpi.yaml `zims_destination`, always
# relative to the media directory), defaulting to `zims`.
ZIMS_DEST="$(MEDIA_DIRECTORY="${MEDIA_DIRECTORY}" "${PROJECT_DIR}/wrolpi/scripts/read_config_value.sh" zims_destination zims)"
ZIM_DIRECTORY="${MEDIA_DIRECTORY}/${ZIMS_DEST}"
LIBRARY="${ZIM_DIRECTORY}/library.xml"

# Wait up to 30 seconds for the zims directory to be mounted.
COUNT=0
while [ ${COUNT} -lt 30 ]; do
  if [ -d "${ZIM_DIRECTORY}" ]; then
    break
  fi
  COUNT=$((COUNT + 1))
  sleep 1
done

# Create the zim directory, if necessary.
[ ! -d "${ZIM_DIRECTORY}" ] && mkdir -p "${ZIM_DIRECTORY}"

# We will replace the library file.
rm -f "${LIBRARY}"

# Import every *.zim.  A corrupt or partial zim is rejected by kiwix-manage
# ("Cannot add zim ..."); it must NOT prevent the remaining valid zims from
# being served, nor stop the server from starting.  So we add each zim
# independently and never abort on a single failure.
found_zim=false
added_zim=false
while IFS= read -r -d '' zim; do
  found_zim=true
  if kiwix-manage "${LIBRARY}" add "${zim}"; then
    added_zim=true
  else
    echo "Skipping zim which could not be added (corrupt or incomplete?): ${zim}" >&2
  fi
done < <(find "${ZIM_DIRECTORY}" -iname '*.zim' -print0)

if [ "${found_zim}" = false ]; then
  echo "Could not find any Zim files to import"
elif [ "${added_zim}" = false ]; then
  echo "Found Zim files but none could be added (all corrupt or incomplete?)" >&2
fi

# When no functioning zim was added, fall back to the default Zim shipped in
# /opt/wrolpi-blobs so the user sees a helpful placeholder ("download some Zim
# files") instead of a blank Kiwix.  A single corrupt zim must never take down
# the server.
if [ "${added_zim}" = false ] && [ -f "${DEFAULT_ZIM}" ]; then
  echo "No usable Zim files found; serving the default WROLPi Zim: ${DEFAULT_ZIM}" >&2
  kiwix-manage "${LIBRARY}" add "${DEFAULT_ZIM}" || echo "Failed to add the default Zim" >&2
fi

# Ensure a library file always exists so kiwix-serve can start even when there
# are no valid zims and the default Zim is missing.
if [ ! -f "${LIBRARY}" ]; then
  printf '<?xml version="1.0" encoding="UTF-8"?>\n<library version="20110515">\n</library>\n' > "${LIBRARY}"
fi

# Serve HTTP kiwix on 9085.  Caddy will serve HTTPS on 8085.
# Bind all interfaces by omitting --address: kiwix-serve defaults to all
# interfaces, and trixie's kiwix-tools 3.7.0 rejects the literal
# "--address 0.0.0.0" ("IP address is not available on this system").
exec kiwix-serve --library "${LIBRARY}" --port 9085
