# The VPN torrents use: a tunnel and its kill switch (controller/vpn/tunnel.py).  The container's network namespace is
# the fail-closed network; the torrent container joins it with `network_mode: service:vpn`.
FROM debian:trixie-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 nftables openvpn wireguard-tools python3 python3-yaml \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY controller/vpn/tunnel.py /app/tunnel.py

ENV PYTHONUNBUFFERED=1
CMD ["python3", "/app/tunnel.py", "run", "--resolv-conf", "/etc/resolv.conf"]
