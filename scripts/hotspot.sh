#! /usr/bin/env bash
# Configure the WROLPi hotspot.
set -x
set -e

apt install -y network-manager

cat >/etc/netplan/50-cloud-init.yaml <<'EOF'
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot.  To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
network:
    version: 2
    renderer: NetworkManager
EOF

cat >/etc/NetworkManager/system-connections/Hotspot.nmconnection <<'EOF'
[connection]
id=Hotspot
uuid=b72ae32e-877c-4559-aaa1-e41a7a9d7bd5
type=wifi
interface-name=wlan0
permissions=
timestamp=1635780305

[wifi]
band=bg
mac-address-blacklist=
mode=ap
seen-bssids=DC:A6:32:C7:01:EE;
ssid=WROLPi

[wifi-security]
key-mgmt=wpa-psk
psk=wrolpi hotspot

[ipv4]
address1=192.168.0.1/24,192.168.0.1
dns-search=
method=shared

[ipv6]
addr-gen-mode=stable-privacy
dns-search=
method=auto

[proxy]
EOF

netplan generate
netplan apply
systemctl restart NetworkManager.service
