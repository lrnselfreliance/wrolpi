#!/usr/bin/env bash
# Generate self-signed SSL certificates for nginx if they don't exist.

set -e

CERT_FILE="/etc/nginx/cert.crt"
KEY_FILE="/etc/nginx/cert.key"

if [[ -f "${CERT_FILE}" && -f "${KEY_FILE}" ]]; then
  echo "Certificates already exist at ${CERT_FILE} and ${KEY_FILE}"
  exit 0
fi

echo "Generating nginx certificates..."
openssl genrsa -out "${KEY_FILE}" 2048
openssl req -new -x509 -nodes -key "${KEY_FILE}" -out "${CERT_FILE}" -days 3650 \
    -subj "/C=US/ST=State/L=City/O=Org/OU=WROLPi/CN=$(hostname).local"
chmod 640 "${KEY_FILE}" "${CERT_FILE}"
echo "Certificates generated successfully."
