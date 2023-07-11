#! /usr/bin/env bash
# This file imports all *.zim files in the media directory, then starts kiwix-serve.

[ ! -d /media/wrolpi ] && echo "Cannot start kiwix without media directory mounted" && exit 1

LIBRARY=/media/wrolpi/zims/library.xml

# Create the zim directory, if necessary.
[ ! -d /media/wrolpi/zims ] && mkdir /media/wrolpi/zims
# We will replace the library file.
rm -f ${LIBRARY}
# Find all Zim files and import them.
find /media/wrolpi -iname '*.zim' -exec kiwix-manage ${LIBRARY} add {} \;

[ ! -f ${LIBRARY} ] && echo "Could not find any Zim files to import" && exit 2

# Serve kiwix on the
kiwix-serve --library ${LIBRARY} --address 0.0.0.0 --port 8085
