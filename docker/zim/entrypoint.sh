#! /usr/bin/env bash
rm -f /library.xml

# Find all Zim files and import them.
find /media/wrolpi -iname '*.zim' -exec /import_zim.sh {} \;

# Bind all interfaces by omitting --address: kiwix-serve defaults to all
# interfaces, and trixie's kiwix-tools 3.7.0 rejects the literal
# "--address 0.0.0.0" ("IP address is not available on this system").
kiwix-serve --monitorLibrary --library /library.xml --port 80
