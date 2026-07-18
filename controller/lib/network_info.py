"""
Network address info for display (e-paper, emergency UI, status).

Returns hostname and IPv4 addresses per interface without bandwidth counters.
"""

from __future__ import annotations

import logging
import socket
from ipaddress import IPv4Address, ip_address
from typing import Optional

import psutil

logger = logging.getLogger(__name__)

# Prefer these interfaces when choosing a single primary address to show.
_PRIMARY_INTERFACE_PREF = (
    "eth0",
    "enp",
    "ens",
    "enx",
    "wlan0",
    "wlp",
    "wlx",
)


def _is_usable_ipv4(addr: str) -> bool:
    """True for global/private IPv4; false for loopback and link-local."""
    try:
        ip = ip_address(addr)
    except ValueError:
        return False
    if not isinstance(ip, IPv4Address):
        return False
    if ip.is_loopback or ip.is_link_local or ip.is_unspecified:
        return False
    return True


def _interface_preference_key(name: str) -> tuple:
    """Sort key: preferred prefixes first, then alphabetical."""
    for i, prefix in enumerate(_PRIMARY_INTERFACE_PREF):
        if name == prefix or name.startswith(prefix):
            return (0, i, name)
    return (1, 99, name)


def get_network_info() -> dict:
    """
    Collect hostname and per-interface IPv4 addresses.

    Returns:
        dict matching NetworkInfoResponse schema
    """
    hostname = socket.gethostname() or "unknown"
    interfaces: list[dict] = []

    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
    except Exception as e:
        logger.warning("Failed to read network interfaces: %s", e)
        return {
            "hostname": hostname,
            "interfaces": [],
            "primary_ipv4": None,
        }

    for name, snics in sorted(addrs.items(), key=lambda item: _interface_preference_key(item[0])):
        if name == "lo":
            continue

        ipv4s: list[str] = []
        for snic in snics:
            # psutil.AF_LINK is MAC; AF_INET is IPv4
            if getattr(snic, "family", None) == socket.AF_INET and snic.address:
                if _is_usable_ipv4(snic.address):
                    ipv4s.append(snic.address)

        if_stats = stats.get(name)
        is_up = bool(if_stats.isup) if if_stats is not None else False

        # Skip interfaces with no usable IPv4 unless they are up (show empty for debugging).
        if not ipv4s and not is_up:
            continue

        interfaces.append({
            "name": name,
            "ipv4": ipv4s,
            "up": is_up,
        })

    primary = _pick_primary_ipv4(interfaces)

    # If nothing usable, fall back to any address including link-local / loopback last resort.
    if primary is None:
        primary = _fallback_any_ipv4(addrs)

    return {
        "hostname": hostname,
        "interfaces": interfaces,
        "primary_ipv4": primary,
    }


def _pick_primary_ipv4(interfaces: list[dict]) -> Optional[str]:
    """First IPv4 on a preferred up interface, else first IPv4 anywhere."""
    # Prefer up interfaces with addresses, in preference order (already sorted).
    for iface in interfaces:
        if iface.get("up") and iface.get("ipv4"):
            return iface["ipv4"][0]
    for iface in interfaces:
        if iface.get("ipv4"):
            return iface["ipv4"][0]
    return None


def _fallback_any_ipv4(addrs: dict) -> Optional[str]:
    """Last-resort primary when all filters exclude everything."""
    for name, snics in addrs.items():
        if name == "lo":
            continue
        for snic in snics:
            if getattr(snic, "family", None) == socket.AF_INET and snic.address:
                return snic.address
    return None
