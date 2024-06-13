#! /usr/bin/env bash
# This file imports all *.zim files in the Zim media directory, then starts kiwix-serve.

[ ! -d /media/wrolpi ] && echo "Cannot start kiwix without media directory mounted" && exit 1

LIBRARY=/media/wrolpi/zims/library.xml

# Wait for the zims directory to be mounted.
COUNT=0
while [ ${COUNT} -lt 30 ]; do
  if [ -d /media/wrolpi/zims ]; then
    break
  fi
  sleep 1
done

# Create the zim directory, if necessary.
[ ! -d /media/wrolpi/zims ] && mkdir /media/wrolpi/zims
# We will replace the library file.
rm -f ${LIBRARY}
# Find all Zim files and import them.
find /media/wrolpi/zims -iname '*.zim' -exec kiwix-manage ${LIBRARY} add {} \;

[ ! -f ${LIBRARY} ] && echo "Could not find any Zim files to import" && exit 2

# Serve HTTP kiwix on 9085.  nginx will serve HTTPS on 8085.
kiwix-serve --library ${LIBRARY} --address 0.0.0.0 --port 9085
