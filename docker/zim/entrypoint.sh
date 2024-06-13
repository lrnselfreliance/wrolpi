#! /usr/bin/env bash
rm -f /library.xml

# Find all Zim files and import them.
find /media/wrolpi -iname '*.zim' -exec /import_zim.sh {} \;

kiwix-serve --monitorLibrary --library /library.xml --address 0.0.0.0 --port 80
