"""
Admin API endpoints for WROLPi Controller.
"""

from fastapi import APIRouter, HTTPException

from controller.api.schemas import (
    BluetoothActionResponse,
    BluetoothStatusResponse,
    DesktopActionResponse,
    DesktopStatusResponse,
    HotspotActionResponse,
    HotspotDevicesResponse,
    HotspotProtocolsResponse,
    HotspotSettingsRequest,
    HotspotSettingsResponse,
    HotspotStatusResponse,
    RestartServicesResponse,
    SambaShareAddRequest,
    SambaShareRemoveResponse,
    SambaShareResponse,
    SambaStatusResponse,
    ServiceRestartResult,
    SystemActionResponse,
    ThrottleActionResponse,
    ThrottleStatusResponse,
    TimezoneSetRequest,
    TimezoneSetResponse,
    TimezoneStatusResponse,
    VncActionResponse,
    VncStatusResponse,
)
from controller.lib.admin import (
    block_bluetooth,
    disable_throttle,
    enable_throttle,
    get_bluetooth_status_dict,
    get_desktop_status_dict,
    get_vnc_status_dict,
    get_device_hotspot_protocols,
    get_hotspot_device,
    get_hotspot_password,
    get_hotspot_protocol,
    get_hotspot_ssid,
    get_hotspot_status_dict,
    get_throttle_status_dict,
    get_timezone_status_dict,
    get_wifi_devices,
    reboot_system,
    restart_all_services,
    set_timezone,
    shutdown_system,
    start_desktop,
    start_hotspot,
    start_vnc,
    stop_desktop,
    stop_hotspot,
    stop_vnc,
    unblock_bluetooth,
    update_hotspot_settings,
)
from controller.lib.config import is_docker_mode
from controller.lib.samba import (
    add_share,
    get_samba_status_dict,
    remove_share,
)

router = APIRouter(tags=["admin"])


def _raise_for_action(result: dict):
    """
    Turn a failed subsystem action into an HTTPException.

    Actions all report `{"success": bool, "error": str}`.  A precondition failure
    (VNC needs a running desktop) is a 409 so callers can tell it from a command
    that was attempted and failed.
    """
    if result.get("success"):
        return
    status_code = 409 if result.get("precondition_failed") else 500
    raise HTTPException(status_code=status_code, detail=result.get("error", "Failed"))


# --- Hotspot ---

@router.get("/api/hotspot/status", response_model=HotspotStatusResponse)
async def hotspot_status() -> HotspotStatusResponse:
    """Get WiFi hotspot status."""
    return HotspotStatusResponse(**get_hotspot_status_dict())


@router.get("/api/hotspot/devices", response_model=HotspotDevicesResponse)
async def hotspot_devices() -> HotspotDevicesResponse:
    """List WiFi devices which could host the hotspot."""
    return HotspotDevicesResponse(devices=get_wifi_devices())


@router.get("/api/hotspot/protocols", response_model=HotspotProtocolsResponse)
async def hotspot_protocols(device: str = None) -> HotspotProtocolsResponse:
    """List the hotspot protocols a WiFi device can host; defaults to the configured device."""
    device = device or get_hotspot_device()
    return HotspotProtocolsResponse(device=device, protocols=get_device_hotspot_protocols(device))


@router.get("/api/hotspot/settings", response_model=HotspotSettingsResponse)
async def hotspot_settings() -> HotspotSettingsResponse:
    """Get WiFi hotspot settings."""
    return HotspotSettingsResponse(
        device=get_hotspot_device(),
        ssid=get_hotspot_ssid(),
        password=get_hotspot_password(),
        protocol=get_hotspot_protocol(),
    )


@router.post("/api/hotspot/settings", response_model=HotspotSettingsResponse)
async def hotspot_settings_update(request: HotspotSettingsRequest) -> HotspotSettingsResponse:
    """Update WiFi hotspot settings; they are saved in controller.yaml."""
    # 500 matches the other subsystem endpoints (hotspot/bluetooth/throttle) in Docker mode.
    if is_docker_mode():
        raise HTTPException(status_code=500, detail="Not available in Docker mode")
    result = update_hotspot_settings(device=request.device, ssid=request.ssid, password=request.password,
                                     protocol=request.protocol)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    return HotspotSettingsResponse(device=result["device"], ssid=result["ssid"], password=result["password"],
                                   protocol=result["protocol"])


@router.post("/api/hotspot/start", response_model=HotspotActionResponse)
async def hotspot_start() -> HotspotActionResponse:
    """Start the WiFi hotspot."""
    result = start_hotspot()
    _raise_for_action(result)
    return HotspotActionResponse(**result)


@router.post("/api/hotspot/stop", response_model=HotspotActionResponse)
async def hotspot_stop() -> HotspotActionResponse:
    """Stop the WiFi hotspot by turning the WiFi radio off."""
    result = stop_hotspot()
    _raise_for_action(result)
    return HotspotActionResponse(**result)


# --- Bluetooth ---

@router.get("/api/bluetooth/status", response_model=BluetoothStatusResponse)
async def bluetooth_status() -> BluetoothStatusResponse:
    """Get Bluetooth radio status."""
    return BluetoothStatusResponse(**await get_bluetooth_status_dict())


@router.post("/api/bluetooth/unblock", response_model=BluetoothActionResponse)
async def bluetooth_unblock() -> BluetoothActionResponse:
    """Unblock the Bluetooth radio (turn it on)."""
    result = await unblock_bluetooth()
    _raise_for_action(result)
    return BluetoothActionResponse(**result)


@router.post("/api/bluetooth/block", response_model=BluetoothActionResponse)
async def bluetooth_block() -> BluetoothActionResponse:
    """Block the Bluetooth radio (turn it off)."""
    result = await block_bluetooth()
    _raise_for_action(result)
    return BluetoothActionResponse(**result)


# --- Desktop ---

@router.get("/api/desktop/status", response_model=DesktopStatusResponse)
async def desktop_status() -> DesktopStatusResponse:
    """Get graphical desktop (display manager) status."""
    return DesktopStatusResponse(**await get_desktop_status_dict())


@router.post("/api/desktop/start", response_model=DesktopActionResponse)
async def desktop_start() -> DesktopActionResponse:
    """Start the graphical desktop until stopped or reboot."""
    result = await start_desktop()
    _raise_for_action(result)
    return DesktopActionResponse(**result)


@router.post("/api/desktop/stop", response_model=DesktopActionResponse)
async def desktop_stop() -> DesktopActionResponse:
    """Stop the graphical desktop; it returns on the next boot (fail open)."""
    result = await stop_desktop()
    _raise_for_action(result)
    return DesktopActionResponse(**result)


# --- VNC ---

@router.get("/api/vnc/status", response_model=VncStatusResponse)
async def vnc_status() -> VncStatusResponse:
    """Get VNC server status."""
    return VncStatusResponse(**await get_vnc_status_dict())


@router.post("/api/vnc/start", response_model=VncActionResponse)
async def vnc_start() -> VncActionResponse:
    """Start the VNC server; requires a running desktop."""
    result = await start_vnc()
    _raise_for_action(result)
    return VncActionResponse(success=True)


@router.post("/api/vnc/stop", response_model=VncActionResponse)
async def vnc_stop() -> VncActionResponse:
    """Stop the VNC server; allowed even when the desktop is stopped."""
    result = await stop_vnc()
    _raise_for_action(result)
    return VncActionResponse(success=True)


# --- Samba ---

@router.get("/api/samba/status", response_model=SambaStatusResponse)
async def samba_status() -> SambaStatusResponse:
    """Get Samba sharing status."""
    return SambaStatusResponse(**get_samba_status_dict())


@router.post("/api/samba/shares", response_model=SambaShareResponse)
async def samba_add_share(request: SambaShareAddRequest) -> SambaShareResponse:
    """Add a Samba share."""
    result = add_share(request.name, request.path, request.read_only, request.comment or "")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    return SambaShareResponse(**result)


@router.delete("/api/samba/shares/{share_name}", response_model=SambaShareRemoveResponse)
async def samba_remove_share(share_name: str) -> SambaShareRemoveResponse:
    """Remove a Samba share."""
    result = remove_share(share_name)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Failed"))
    return SambaShareRemoveResponse(**result)


# --- Throttle ---

@router.get("/api/throttle/status", response_model=ThrottleStatusResponse)
async def throttle_status() -> ThrottleStatusResponse:
    """Get CPU throttle status."""
    return ThrottleStatusResponse(**get_throttle_status_dict())


@router.post("/api/throttle/enable", response_model=ThrottleActionResponse)
async def throttle_enable() -> ThrottleActionResponse:
    """Enable CPU throttle (powersave mode)."""
    result = enable_throttle()
    _raise_for_action(result)
    return ThrottleActionResponse(**result)


@router.post("/api/throttle/disable", response_model=ThrottleActionResponse)
async def throttle_disable() -> ThrottleActionResponse:
    """Disable CPU throttle (normal performance)."""
    result = disable_throttle()
    _raise_for_action(result)
    return ThrottleActionResponse(**result)


# --- Timezone ---

@router.get("/api/timezone/status", response_model=TimezoneStatusResponse)
async def timezone_status() -> TimezoneStatusResponse:
    """Get current system timezone."""
    return TimezoneStatusResponse(**get_timezone_status_dict())


@router.post("/api/timezone/set", response_model=TimezoneSetResponse)
async def timezone_set(request: TimezoneSetRequest) -> TimezoneSetResponse:
    """Set the system timezone."""
    result = set_timezone(request.timezone)
    _raise_for_action(result)
    return TimezoneSetResponse(**result)


# --- System Control ---

@router.post("/api/shutdown", response_model=SystemActionResponse)
async def system_shutdown() -> SystemActionResponse:
    """Shut down the system."""
    if is_docker_mode():
        raise HTTPException(
            status_code=501,
            detail="Cannot shutdown from Docker container"
        )

    result = shutdown_system()
    _raise_for_action(result)
    return SystemActionResponse(**result)


@router.post("/api/reboot", response_model=SystemActionResponse)
async def system_reboot() -> SystemActionResponse:
    """Reboot the system."""
    if is_docker_mode():
        raise HTTPException(
            status_code=501,
            detail="Cannot reboot from Docker container"
        )

    result = reboot_system()
    _raise_for_action(result)
    return SystemActionResponse(**result)


@router.post("/api/restart", response_model=RestartServicesResponse)
async def services_restart() -> RestartServicesResponse:
    """Restart all WROLPi services including Controller."""
    if is_docker_mode():
        raise HTTPException(
            status_code=501,
            detail="Service restart via systemctl not available in Docker mode"
        )

    result = await restart_all_services()
    # Convert nested dicts to Pydantic models
    services = {
        name: ServiceRestartResult(**status)
        for name, status in result.get("services", {}).items()
    }
    return RestartServicesResponse(
        success=result.get("success", False),
        services=services,
        error=result.get("error"),
    )
