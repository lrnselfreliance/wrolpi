#!/usr/bin/env bash
# Check if the WROLPi leaf certificate is expired or expiring within 30 days.
# If so, regenerate it and reload Caddy.

set -e

CERT_DIR="${CERT_DIR:-/etc/ssl/wrolpi}"
LEAF_CERT="${CERT_DIR}/cert.crt"

if [ ! -f "${LEAF_CERT}" ]; then
  echo "Leaf certificate not found at ${LEAF_CERT}, generating..."
  /opt/wrolpi/scripts/generate_certificates.sh
  systemctl reload caddy || systemctl restart caddy || echo "Warning: failed to reload Caddy"
  exit 0
fi

# Check if cert expires within 30 days.
if openssl x509 -checkend 2592000 -noout -in "${LEAF_CERT}" 2>/dev/null; then
  echo "Certificate is still valid for more than 30 days, no renewal needed."
  exit 0
fi

echo "Certificate is expired or expiring within 30 days, renewing..."
/opt/wrolpi/scripts/generate_certificates.sh

# Reload Caddy to pick up new cert.
systemctl reload caddy || systemctl restart caddy || echo "Warning: failed to reload Caddy"
echo "Certificate renewed and Caddy reloaded."
