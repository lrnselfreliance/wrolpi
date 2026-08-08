# Pinned to the Caddy that Debian 13 devices run, so Docker matches hardware.
FROM caddy:2.11.4

RUN apk add --no-cache openssl bash

# Copy scripts and static files.
COPY docker/web/Caddyfile /etc/caddy/Caddyfile
COPY docker/web/entrypoint.sh /entrypoint.sh
COPY scripts/generate_certificates.sh /opt/wrolpi/scripts/generate_certificates.sh

RUN chmod +x /entrypoint.sh /opt/wrolpi/scripts/generate_certificates.sh

ENTRYPOINT ["/entrypoint.sh"]
