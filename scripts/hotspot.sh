#! /usr/bin/env bash
# Configure the hotspot.
set -x
set -e

cat >>/etc/udev/rules.d/70-ap-interface.rules <<'EOF'
SUBSYSTEM=="net", KERNEL=="wlan*", ACTION=="add", RUN+="/sbin/iw dev %k interface add ap%n type __ap"
EOF

cat >>/etc/systemd/network/20-ap0.network <<'EOF'
[Match]
Name=ap0

[Network]
Address=192.168.1.1/28
DHCPServer=yes
EOF

sudo udevadm trigger --action=add /sys/class/net/wlan0
sudo systemctl restart systemd-networkd

cat >/etc/systemd/system/hostapd@.service <<'EOF'
[Unit]
Description=Advanced IEEE 802.11 AP and IEEE 802.1X/WPA/WPA2/EAP Authenticator
Requires=sys-subsystem-net-devices-%i.device
After=sys-subsystem-net-devices-%i.device
Before=network.target
Wants=network.target

[Service]
Type=simple
ExecStart=/usr/sbin/hostapd /etc/hostapd/hostapd-%I.conf

[Install]
Alias=multi-user.target.wants/hostapd@%i.service
EOF

cat >/etc/hostapd/hostapd-ap0.conf <<'EOF'
interface=ap0
country_code=US
hw_mode=g

ssid=wrolpi
channel=6
ignore_broadcast_ssid=0

auth_algs=1
wpa=2
wpa_passphrase=wrolpi
wpa_key_mgmt=WPA-PSK

wmm_enabled=0
EOF

mkdir /etc/systemd/system/wpa_supplicant@wlan0.service.d
cat >/etc/systemd/system/wpa_supplicant@wlan0.service.d/override.conf <<'EOF'
[Unit]
Wants=hostapd@ap0.service
After=hostapd@ap0.service

[Service]
ExecStartPre=/bin/sleep 3
EOF

sudo systemctl enable hostapd@ap0
sudo systemctl start hostapd@ap0
