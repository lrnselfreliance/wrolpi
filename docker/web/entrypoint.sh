#!/bin/sh
export MEDIA_DIRECTORY="${MEDIA_DIRECTORY:-/opt/media}"
export CERT_DIR="/etc/ssl/caddy"
/opt/wrolpi/scripts/generate_certificates.sh
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
