#!/usr/bin/env bash
# Adds Caddy's apt repository, trusting the key committed with WROLPi instead of one downloaded over TLS (a forged
# certificate could serve a key that signs other caddy packages).  The ISO uses the same key through live-build:
# debian-live-config/config/archives/caddy-stable.key, fingerprint 65760C51EDEA2017CEA2CA15155B6D79CA56EA34.
set -e

PROJECT_DIR=$(dirname "$(dirname "$(realpath "$0")")")

# apt reads an ASCII-armored key only from a .asc file.
install -m 644 "${PROJECT_DIR}/debian-live-config/config/archives/caddy-stable.key" /usr/share/keyrings/caddy-stable-archive-keyring.asc
echo 'deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.asc] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main' \
  >/etc/apt/sources.list.d/caddy-stable.list
