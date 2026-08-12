# Pinned to the Caddy that Debian 13 devices run, so Docker matches hardware.
FROM caddy:2.11.4

RUN apk add --no-cache openssl bash curl

# The planet overview blob, which Caddy serves at /blobs/map-overview.pmtiles.
#
# It is the world at zoom 0-6, and it is what a regional map extract sits on top of: without
# it a user who subscribes to, say, three US regions gets those regions floating on an empty
# background at every zoom level that does not have their data.  Only a full planet file (134
# GB) makes it unnecessary.
#
# Raspberry Pi and Debian installs get this from pi-gen, the live-build config, and
# upgrade.sh.  Docker had no equivalent and shipped without it -- see
# modules/map/test/test_map_overview_blob.py.  42 MB.
#
# `curl -f` so an HTTP error fails this layer rather than writing the error body to the file
# and exiting 0; an image that builds without the blob is the bug all over again, except now
# it is silent at build time too.
RUN mkdir -p /opt/wrolpi-blobs && \
    curl -fsSL https://wrolpi.nyc3.cdn.digitaloceanspaces.com/maps/map-overview.pmtiles \
    -o /opt/wrolpi-blobs/map-overview.pmtiles && \
    [ -s /opt/wrolpi-blobs/map-overview.pmtiles ]

# Copy scripts and static files.
COPY docker/web/Caddyfile /etc/caddy/Caddyfile
COPY docker/web/entrypoint.sh /entrypoint.sh
COPY scripts/generate_certificates.sh /opt/wrolpi/scripts/generate_certificates.sh

RUN chmod +x /entrypoint.sh /opt/wrolpi/scripts/generate_certificates.sh

ENTRYPOINT ["/entrypoint.sh"]
