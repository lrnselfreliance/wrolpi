FROM caddy:latest

RUN apk add --no-cache openssl bash

# Copy scripts and static files.
COPY docker/web/Caddyfile /etc/caddy/Caddyfile
COPY docker/web/entrypoint.sh /entrypoint.sh
COPY scripts/generate_certificates.sh /opt/wrolpi/scripts/generate_certificates.sh
COPY etc/raspberrypios/landing.html /var/www/landing.html

RUN chmod +x /entrypoint.sh /opt/wrolpi/scripts/generate_certificates.sh

ENTRYPOINT ["/entrypoint.sh"]
