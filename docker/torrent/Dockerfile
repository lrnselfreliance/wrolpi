# Torrents (qBittorrent).  The container joins the `vpn` container's network (`network_mode: service:vpn`), whose kill
# switch lets nothing out except through the VPN tunnel.  Its WebUI (8091) is served to the LAN by Caddy.
FROM debian:trixie-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends qbittorrent-nox python3 iproute2 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY modules/torrents/qbittorrent_prepare.py /app/qbittorrent_prepare.py

ENV PROFILE=/media/wrolpi/config/qbittorrent
CMD ["sh", "-c", "python3 /app/qbittorrent_prepare.py --profile \"$PROFILE\" && exec qbittorrent-nox --confirm-legal-notice --profile=\"$PROFILE\""]
