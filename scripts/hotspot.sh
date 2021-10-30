#! /usr/bin/env bash
# Configure the WROLPi hotspot.
set -x
set -e

cat >/etc/NetworkManager/system-connections/Hotspot.nmconnection <<'EOF'
[connection]
id=Hotspot
uuid=f8309ae2-cb53-480d-a921-fea698fb8ac8
type=wifi
permissions=

[wifi]
mac-address-blacklist=
mode=ap
ssid=WROLPi

[wifi-security]
key-mgmt=wpa-psk
psk=wrolpihotspot

[ipv4]
dns-search=
method=shared

[ipv6]
addr-gen-mode=stable-privacy
dns-search=
ip6-privacy=0
method=shared

[proxy]
EOF

systemctl restart NetworkManager.service
