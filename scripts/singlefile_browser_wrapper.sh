#!/bin/sh
# Runs the browser for single-file with stderr discarded.
#
# single-file spawns the browser with piped stderr that it never reads; under Deno >= 2.3 this
# kills the browser during startup (the CDP port never opens and single-file fails with
# "tcp connect error: Connection refused").  WROLPi passes this wrapper as the
# --browser-executable-path and provides the real browser via WROLPI_BROWSER.
exec "${WROLPI_BROWSER}" "$@" 2>/dev/null
