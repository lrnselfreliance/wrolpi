#!/usr/bin/env bash
# Generate a root CA and signed leaf certificate for WROLPi.
#
# Root CA:   stored in ${MEDIA_DIRECTORY}/config/ssl/ — persists forever.
# Leaf cert: stored in ${CERT_DIR}/ — regenerated each run to pick up hostname/IP changes.
#
# Users trust the root CA once; leaf certs can be regenerated without re-trusting.

set -e

MEDIA_DIRECTORY="${MEDIA_DIRECTORY:-/media/wrolpi}"
CERT_DIR="${CERT_DIR:-/etc/ssl/wrolpi}"

CA_DIR="${MEDIA_DIRECTORY}/config/ssl"
CA_KEY="${CA_DIR}/ca.key"
CA_CERT="${CA_DIR}/ca.crt"

LEAF_KEY="${CERT_DIR}/cert.key"
LEAF_CERT="${CERT_DIR}/cert.crt"

mkdir -p "${CA_DIR}" "${CERT_DIR}"

# --- Root CA (only created once) ---
if [[ -f "${CA_CERT}" && -f "${CA_KEY}" ]]; then
  echo "Root CA already exists at ${CA_CERT}"
else
  echo "Generating WROLPi Root CA..."
  openssl genrsa -out "${CA_KEY}" 4096
  openssl req -new -x509 -nodes -key "${CA_KEY}" -out "${CA_CERT}" -days 36500 \
      -subj "/C=US/ST=State/L=City/O=WROLPi/CN=WROLPi Root CA" \
      -addext "basicConstraints = critical, CA:TRUE" \
      -addext "keyUsage = critical, keyCertSign, cRLSign" \
      -addext "nameConstraints = critical, permitted;DNS:.local, permitted;DNS:localhost, permitted;IP:127.0.0.0/255.0.0.0, permitted;IP:10.0.0.0/255.0.0.0, permitted;IP:172.16.0.0/255.240.0.0, permitted;IP:192.168.0.0/255.255.0.0, permitted;IP:::1/ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff, permitted;IP:fc00::/fe00::, permitted;IP:fe80::/ffc0::"
  chmod 600 "${CA_KEY}"
  chmod 644 "${CA_CERT}"
  echo "Root CA generated."
fi

# --- Leaf certificate (always regenerated) ---
echo "Generating WROLPi leaf certificate..."

# Build SAN list dynamically.
SAN="DNS:localhost,DNS:wrolpi.local"

HOSTNAME_SHORT="$(hostname)"
if [[ -n "${HOSTNAME_SHORT}" ]]; then
  SAN="${SAN},DNS:${HOSTNAME_SHORT}.local"
fi

SAN="${SAN},IP:127.0.0.1"

# Add all local IPs.
for ip in $(hostname -I 2>/dev/null || true); do
  SAN="${SAN},IP:${ip}"
done

# Append any extra SANs (e.g. host IP when running in Docker).
if [[ -n "${EXTRA_SANS:-}" ]]; then
  SAN="${SAN},${EXTRA_SANS}"
fi

echo "SANs: ${SAN}"

# Create CSR and sign with root CA.
openssl genrsa -out "${LEAF_KEY}" 2048

openssl req -new -key "${LEAF_KEY}" \
    -subj "/C=US/ST=State/L=City/O=WROLPi/CN=${HOSTNAME_SHORT:-wrolpi}.local" \
    -out "${CERT_DIR}/cert.csr"

openssl x509 -req -in "${CERT_DIR}/cert.csr" \
    -CA "${CA_CERT}" -CAkey "${CA_KEY}" -CAcreateserial \
    -days 825 \
    -extfile <(printf "subjectAltName=%s\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth" "${SAN}") \
    -out "${LEAF_CERT}"

rm -f "${CERT_DIR}/cert.csr"
chmod 640 "${LEAF_KEY}" "${LEAF_CERT}"

# Allow the caddy user to read the leaf cert/key (native installs).
if id caddy >/dev/null 2>&1; then
  chown root:caddy "${LEAF_KEY}" "${LEAF_CERT}"
fi

# Validate the chain.
openssl verify -CAfile "${CA_CERT}" "${LEAF_CERT}"
echo "Leaf certificate generated and verified."

# Install root CA into system trust store so the device trusts its own certs.
if command -v update-ca-certificates >/dev/null 2>&1; then
  cp "${CA_CERT}" /usr/local/share/ca-certificates/wrolpi-ca.crt
  update-ca-certificates
  echo "Root CA installed in system trust store."
fi
