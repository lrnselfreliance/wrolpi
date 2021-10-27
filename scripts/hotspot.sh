#! /usr/bin/env bash
# Configure the WROLPi hotspot.
set -x
set -e

apt install hostapd isc-dhcp-server

# hostapd will broadcast the hotspot
cat >/etc/hostapd/hostapd.conf <<'EOF'
# the interface used by the AP
interface=wlan0
driver=nl80211
hw_mode=g
# the channel to use
channel=1
# limit the frequencies used to those allowed in the country
ieee80211d=1
# the country code
country_code=US
# 802.11n support
ieee80211n=1
# QoS support
wmm_enabled=1
# the name of the AP
ssid=WROLPi
macaddr_acl=0
# 1=wpa, 2=wep, 3=both
auth_algs=1
ignore_broadcast_ssid=0
# WPA2 only
wpa=2
wpa_passphrase=wrolpihotspot
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF

# Serve DHCP on the hotspot interface.
cat >/etc/dhcp/dhcpd.conf <<'EOF'
default-lease-time 600;
max-lease-time 7200;

subnet 192.168.1.0 netmask 255.255.255.0 {
 range 192.168.1.100 192.168.1.200;
 option routers 192.168.1.1;
 option domain-name-servers 192.168.1.1, 192.168.1.2;
 option domain-name "wrolpi.local";
}
EOF
sed -ie 's/INTERFACESv4.*/INTERFACESv4="wlan0"/' /etc/default/isc-dhcp-server

# Configure eth0 as a normal dhcp interface, wlan0 as our hotspot interface.
cat >/etc/netplan/10-wrolpi-hotspot.yaml <<'EOF'
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: yes
    wlan0:
      dhcp4: no
      dhcp6: no
      addresses:
        - 192.168.1.1/24
EOF

netplan generate && netplan apply && systemctl unmask hostapd.service &&
  systemctl restart hostapd.service isc-dhcp-server.service
