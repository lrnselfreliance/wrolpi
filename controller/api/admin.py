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
    WrolModeActionResponse,
    WrolModeStatusResponse,
    HotspotDevicesResponse,
    HotspotSettingsRequest,
    HotspotSettingsResponse,
    HotspotStatusResponse,
    NetworkInfoResponse,
    RestartServicesResponse,
    SambaShareAddRequest,
    SambaShareRemoveResponse,
    SambaShareResponse,
    SambaStatusResponse,
    ServiceRestartResult,
    SshActionResponse,
    SshStatusResponse,
    SystemActionResponse,
    ThrottleActionResponse,
    ThrottleStatusResponse,
    TimezoneSetRequest,
    TimezoneSetResponse,
    TimezoneStatusResponse,
)
from controller.lib.admin import (
    disable_bluetooth,
    disable_hotspot,
    disable_throttle,
    enable_bluetooth,
    enable_hotspot,
    enable_throttle,
    get_bluetooth_status_dict,
    get_hotspot_device,
    get_hotspot_password,
    get_hotspot_ssid,
    get_hotspot_status_dict,
    get_throttle_status_dict,
    get_timezone_status_dict,
    get_wifi_devices,
    reboot_system,
    restart_all_services,
    set_timezone,
    shutdown_system,
    update_hotspot_settings,
)
from controller.lib.config import is_docker_mode
from controller.lib.desktop import (
    disable_desktop,
    enable_desktop,
    get_desktop_status_dict,
)
from controller.lib.network_info import get_network_info
from controller.lib.samba import (
    add_share,
    get_samba_status_dict,
    remove_share,
)
from controller.lib.ssh import (
    disable_ssh,
    enable_ssh,
    get_ssh_status_dict,
)
from controller.lib.wrol_mode import (
    disable_wrol_mode,
    enable_wrol_mode,
    get_wrol_mode_status_dict,
)

router = APIRouter(tags=["admin"])


# --- Hotspot ---

@router.get("/api/hotspot/status", response_model=HotspotStatusResponse)
async def hotspot_status() -> HotspotStatusResponse:
    """Get WiFi hotspot status."""
    return HotspotStatusResponse(**get_hotspot_status_dict())


@router.get("/api/hotspot/devices", response_model=HotspotDevicesResponse)
async def hotspot_devices() -> HotspotDevicesResponse:
    """List WiFi devices which could host the hotspot."""
    return HotspotDevicesResponse(devices=get_wifi_devices())


@router.get("/api/hotspot/settings", response_model=HotspotSettingsResponse)
async def hotspot_settings() -> HotspotSettingsResponse:
    """Get WiFi hotspot settings."""
    return HotspotSettingsResponse(
        device=get_hotspot_device(),
        ssid=get_hotspot_ssid(),
        password=get_hotspot_password(),
    )


@router.post("/api/hotspot/settings", response_model=HotspotSettingsResponse)
async def hotspot_settings_update(request: HotspotSettingsRequest) -> HotspotSettingsResponse:
    """Update WiFi hotspot settings; they are saved in controller.yaml."""
    # 500 matches the other subsystem endpoints (hotspot/bluetooth/throttle) in Docker mode.
    if is_docker_mode():
        raise HTTPException(status_code=500, detail="Not available in Docker mode")
    result = update_hotspot_settings(device=request.device, ssid=request.ssid, password=request.password)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    return HotspotSettingsResponse(device=result["device"], ssid=result["ssid"], password=result["password"])


@router.post("/api/hotspot/enable", response_model=HotspotActionResponse)
async def hotspot_enable() -> HotspotActionResponse:
    """Enable WiFi hotspot."""
    result = enable_hotspot()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
    return HotspotActionResponse(**result)


@router.post("/api/hotspot/disable", response_model=HotspotActionResponse)
async def hotspot_disable() -> HotspotActionResponse:
    """Disable WiFi hotspot."""
    result = disable_hotspot()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
    return HotspotActionResponse(**result)


# --- Bluetooth ---

@router.get("/api/bluetooth/status", response_model=BluetoothStatusResponse)
async def bluetooth_status() -> BluetoothStatusResponse:
    """Get Bluetooth radio status."""
    return BluetoothStatusResponse(**await get_bluetooth_status_dict())


@router.post("/api/bluetooth/enable", response_model=BluetoothActionResponse)
async def bluetooth_enable() -> BluetoothActionResponse:
    """Enable Bluetooth radio."""
    result = await enable_bluetooth()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
    return BluetoothActionResponse(**result)


@router.post("/api/bluetooth/disable", response_model=BluetoothActionResponse)
async def bluetooth_disable() -> BluetoothActionResponse:
    """Disable Bluetooth radio."""
    result = await disable_bluetooth()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
    return BluetoothActionResponse(**result)


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
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
    return ThrottleActionResponse(**result)


@router.post("/api/throttle/disable", response_model=ThrottleActionResponse)
async def throttle_disable() -> ThrottleActionResponse:
    """Disable CPU throttle (normal performance)."""
    result = disable_throttle()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
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
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
    return TimezoneSetResponse(**result)


# --- Network info (addresses for display) ---

@router.get("/api/network/info", response_model=NetworkInfoResponse)
async def network_info() -> NetworkInfoResponse:
    """Hostname and IPv4 addresses for status displays (e-paper, emergency UI)."""
    return NetworkInfoResponse(**get_network_info())


# --- SSH (runtime start/stop only; fail open on reboot) ---

@router.get("/api/ssh/status", response_model=SshStatusResponse)
async def ssh_status() -> SshStatusResponse:
    """Get SSH daemon status (enabled = currently running)."""
    return SshStatusResponse(**get_ssh_status_dict())


@router.post("/api/ssh/enable", response_model=SshActionResponse)
async def ssh_enable() -> SshActionResponse:
    """Start SSH for this session only (does not enable at boot)."""
    result = enable_ssh()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
    return SshActionResponse(**result)


@router.post("/api/ssh/disable", response_model=SshActionResponse)
async def ssh_disable() -> SshActionResponse:
    """Stop SSH for this session only (does not disable at boot; returns after reboot)."""
    result = disable_ssh()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
    return SshActionResponse(**result)


# --- Desktop (runtime start/stop only; fail open on reboot) ---

@router.get("/api/desktop/status", response_model=DesktopStatusResponse)
async def desktop_status() -> DesktopStatusResponse:
    """Get desktop/display-manager status (enabled = currently running)."""
    return DesktopStatusResponse(**get_desktop_status_dict())


@router.post("/api/desktop/enable", response_model=DesktopActionResponse)
async def desktop_enable() -> DesktopActionResponse:
    """Start the display manager for this session only (does not change default target)."""
    result = enable_desktop()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
    return DesktopActionResponse(**result)


@router.post("/api/desktop/disable", response_model=DesktopActionResponse)
async def desktop_disable() -> DesktopActionResponse:
    """Stop the display manager for this session only (desktop returns after reboot)."""
    result = disable_desktop()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
    return DesktopActionResponse(**result)


# --- WROL Mode ---

@router.get("/api/wrol-mode", response_model=WrolModeStatusResponse)
@router.get("/api/wrol-mode/status", response_model=WrolModeStatusResponse)
async def wrol_mode_status() -> WrolModeStatusResponse:
    """Get WROL Mode status (yaml + flag file)."""
    return WrolModeStatusResponse(**get_wrol_mode_status_dict())


@router.post("/api/wrol-mode/enable", response_model=WrolModeActionResponse)
async def wrol_mode_enable() -> WrolModeActionResponse:
    """Enable WROL Mode (flag file, wrolpi.yaml, best-effort main API notify)."""
    result = enable_wrol_mode()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
    return WrolModeActionResponse(**result)


@router.post("/api/wrol-mode/disable", response_model=WrolModeActionResponse)
async def wrol_mode_disable() -> WrolModeActionResponse:
    """Disable WROL Mode (flag file, wrolpi.yaml, best-effort main API notify)."""
    result = disable_wrol_mode()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
    return WrolModeActionResponse(**result)


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
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
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
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
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
