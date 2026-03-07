#!/bin/sh
export MEDIA_DIRECTORY="${MEDIA_DIRECTORY:-/opt/media}"
export CERT_DIR="/etc/ssl/caddy"

# EXTRA_SANS can be set to include additional SANs in the leaf certificate.
# This is needed in Docker because the container cannot discover the host's
# real LAN IP.  Example: EXTRA_SANS=IP:10.0.0.5,DNS:myhost.local
export EXTRA_SANS="${EXTRA_SANS:-}"

/opt/wrolpi/scripts/generate_certificates.sh
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
