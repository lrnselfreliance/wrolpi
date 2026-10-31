#!/usr/bin/env bash
# Usage: install_npm_tools.sh [NPM_TOOLS_DIR]
#
# Installs the npm command-line tools WROLPi runs (serve, single-file, readability-extractor) from the committed
# npm-tools/package-lock.json.  `npm ci` checks every package against its sha512 in the lockfile, so a forged TLS
# certificate for the registry cannot change them; `npm i -g` resolved the whole dependency tree fresh.  The commands
# are linked into /usr/local/bin, where WROLPi, help.sh and the systemd units find them.
set -e

NPM_TOOLS=${1:-$(dirname "$(dirname "$(realpath "$0")")")/npm-tools}

npm ci --prefix "${NPM_TOOLS}" --omit=dev --no-audit --no-fund
# Remove the copies older WROLPi versions installed globally (in /usr/bin on Raspberry Pi OS) so they cannot be found
# instead of these.
npm rm -g serve single-file-cli readability-extractor >/dev/null 2>&1 || :
for command in serve single-file readability-extractor; do
  ln -sf "${NPM_TOOLS}/node_modules/.bin/${command}" "/usr/local/bin/${command}"
done
