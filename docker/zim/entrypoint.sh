#! /usr/bin/env bash
set -u

LIBRARY=/library.xml
# Default Zim baked into the image; served when no real zim is available.
DEFAULT_ZIM="${DEFAULT_ZIM:-/opt/wrolpi-blobs/default.zim}"

rm -f "${LIBRARY}"

# Import every *.zim under the mounted media directory.  A corrupt or partial
# zim is rejected by kiwix-manage; skip it so the remaining valid zims are
# still served.  We scan the whole media mount, so any configured
# `zims_destination` subdirectory is covered automatically -- no config read.
added_zim=false
while IFS= read -r -d '' zim; do
  if /import_zim.sh "${zim}"; then
    added_zim=true
  else
    echo "Skipping zim which could not be added (corrupt or incomplete?): ${zim}" >&2
  fi
done < <(find /media/wrolpi -iname '*.zim' -print0)

# When no functioning zim was added, fall back to the default Zim so the user
# sees a helpful placeholder instead of a blank Kiwix.
if [ "${added_zim}" = false ] && [ -f "${DEFAULT_ZIM}" ]; then
  echo "No usable Zim files found; serving the default WROLPi Zim: ${DEFAULT_ZIM}" >&2
  /import_zim.sh "${DEFAULT_ZIM}" || echo "Failed to add the default Zim" >&2
fi

# Ensure a library file always exists so kiwix-serve can start regardless.
if [ ! -f "${LIBRARY}" ]; then
  printf '<?xml version="1.0" encoding="UTF-8"?>\n<library version="20110515">\n</library>\n' > "${LIBRARY}"
fi

# Bind all interfaces by omitting --address: kiwix-serve defaults to all
# interfaces, and trixie's kiwix-tools 3.7.0 rejects the literal
# "--address 0.0.0.0" ("IP address is not available on this system").
kiwix-serve --monitorLibrary --library "${LIBRARY}" --port 80
