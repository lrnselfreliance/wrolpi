"""
VPN API endpoints for WROLPi Controller.  Torrents only reach the Internet through this VPN.
"""

import asyncio

from fastapi import APIRouter, HTTPException

from controller.api.schemas import (
    VpnAuthRequest,
    VpnConfigUploadRequest,
    VpnSettingsRequest,
    VpnSettingsResponse,
    VpnStatusResponse,
)
from controller.lib import vpn
from controller.vpn.tunnel import VPNConfigError

router = APIRouter(tags=["vpn"])


async def _call(func, *args, **kwargs):
    """Run a settings change off the event loop (saving looks up the VPN servers), as a 400 when it is refused."""
    try:
        return await asyncio.to_thread(func, *args, **kwargs)
    except VPNConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        # e.g. the primary drive is not mounted, so controller.yaml cannot be saved.
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/api/vpn/status", response_model=VpnStatusResponse)
async def vpn_status() -> VpnStatusResponse:
    """Whether torrents can reach the Internet, and the address peers see."""
    return VpnStatusResponse(**vpn.get_vpn_status())


@router.get("/api/vpn/settings", response_model=VpnSettingsResponse)
async def vpn_settings() -> VpnSettingsResponse:
    return VpnSettingsResponse(**vpn.get_vpn_settings_response())


@router.post("/api/vpn/settings", response_model=VpnSettingsResponse)
async def update_vpn_settings(request: VpnSettingsRequest) -> VpnSettingsResponse:
    return VpnSettingsResponse(**await _call(vpn.update_vpn_settings, **request.model_dump()))


@router.post("/api/vpn/config", response_model=VpnSettingsResponse)
async def upload_vpn_config(request: VpnConfigUploadRequest) -> VpnSettingsResponse:
    """Store a WireGuard .conf or OpenVPN .ovpn, replacing the previous config."""
    return VpnSettingsResponse(**await _call(vpn.save_vpn_config, request.filename, request.content))


@router.delete("/api/vpn/config", response_model=VpnSettingsResponse)
async def delete_vpn_config() -> VpnSettingsResponse:
    """Forget the VPN config and login, and turn the VPN off."""
    return VpnSettingsResponse(**await _call(vpn.delete_vpn_config))


@router.post("/api/vpn/auth", response_model=VpnSettingsResponse)
async def save_vpn_auth(request: VpnAuthRequest) -> VpnSettingsResponse:
    return VpnSettingsResponse(**await _call(vpn.save_openvpn_auth, request.username, request.password))
