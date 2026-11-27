#!/usr/bin/env bash
# Creates (up) or removes (down) the `wrolpi-vpn` network namespace which torrents live in.
#
# The namespace reaches the Internet only through a veth pair to this host, which masquerades it.  The namespace's own
# kill switch (controller/vpn/tunnel.py) lets that path carry nothing but the VPN's traffic to its servers, so
# everything else in the namespace must use the tunnel.  The host reaches the namespace (the torrent client's WebUI)
# at 10.211.0.2.
#
# Idempotent: `up` is safe to run while the namespace exists.  The namespace (and its kill switch) is left in place
# when wrolpi-vpn.service stops or restarts, so a crashed tunnel never opens a way out.
set -euo pipefail

NAMESPACE=wrolpi-vpn
HOST_INTERFACE=veth-wrolpi
NAMESPACE_INTERFACE=vpn-uplink
HOST_ADDRESS=10.211.0.1
NAMESPACE_ADDRESS=10.211.0.2
NETWORK=10.211.0.0/30

up() {
  if [ ! -e "/run/netns/${NAMESPACE}" ]; then
    ip netns add "${NAMESPACE}"
  fi

  # `ip netns exec` bind-mounts this over /etc/resolv.conf inside the namespace, but only if it exists.  The tunnel
  # writes the VPN's DNS servers here; until then the namespace has none, so nothing leaks a lookup.
  mkdir -p "/etc/netns/${NAMESPACE}"
  if [ ! -e "/etc/netns/${NAMESPACE}/resolv.conf" ]; then
    : >"/etc/netns/${NAMESPACE}/resolv.conf"
  fi

  if ! ip link show "${HOST_INTERFACE}" &>/dev/null; then
    ip link add "${HOST_INTERFACE}" type veth peer name "${NAMESPACE_INTERFACE}" netns "${NAMESPACE}"
  fi
  ip address replace "${HOST_ADDRESS}/30" dev "${HOST_INTERFACE}"
  ip link set "${HOST_INTERFACE}" up

  ip -n "${NAMESPACE}" link set lo up
  ip -n "${NAMESPACE}" address replace "${NAMESPACE_ADDRESS}/30" dev "${NAMESPACE_INTERFACE}"
  ip -n "${NAMESPACE}" link set "${NAMESPACE_INTERFACE}" up
  ip -n "${NAMESPACE}" route replace default via "${HOST_ADDRESS}" dev "${NAMESPACE_INTERFACE}"
  # The uplink carries IPv4 only; the tunnel may bring IPv6.
  ip netns exec "${NAMESPACE}" sh -c "echo 1 >/proc/sys/net/ipv6/conf/${NAMESPACE_INTERFACE}/disable_ipv6"

  # The host forwards the namespace's traffic.  (The hotspot turns this on too, so it is never turned off here.)
  echo 1 >/proc/sys/net/ipv4/ip_forward
  nft -f - <<EOF
table inet wrolpi_vpn_host
delete table inet wrolpi_vpn_host
table inet wrolpi_vpn_host {
	chain postrouting {
		type nat hook postrouting priority srcnat; policy accept;
		ip saddr ${NETWORK} oifname != "${HOST_INTERFACE}" masquerade
	}
	chain forward {
		# Only the namespace's own traffic is touched; the host's other forwarding (e.g. the hotspot) is not.
		type filter hook forward priority filter; policy accept;
		iifname "${HOST_INTERFACE}" ip saddr != ${NAMESPACE_ADDRESS} drop
		oifname "${HOST_INTERFACE}" ct state established,related accept
		oifname "${HOST_INTERFACE}" drop
	}
}
EOF
}

down() {
  ip netns delete "${NAMESPACE}" 2>/dev/null || :
  ip link delete "${HOST_INTERFACE}" 2>/dev/null || :
  nft delete table inet wrolpi_vpn_host 2>/dev/null || :
}

case "${1:-}" in
up) up ;;
down) down ;;
*)
  echo "Usage: $0 up|down" >&2
  exit 2
  ;;
esac
