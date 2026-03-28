"""
Admin API endpoints for WROLPi Controller.
"""

from fastapi import APIRouter, HTTPException

from controller.api.schemas import (
    BluetoothActionResponse,
    BluetoothStatusResponse,
    HotspotActionResponse,
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
)
from controller.lib.admin import (
    disable_bluetooth,
    disable_hotspot,
    disable_throttle,
    enable_bluetooth,
    enable_hotspot,
    enable_throttle,
    get_bluetooth_status_dict,
    get_hotspot_status_dict,
    get_throttle_status_dict,
    get_timezone_status_dict,
    reboot_system,
    restart_all_services,
    set_timezone,
    shutdown_system,
)
from controller.lib.config import is_docker_mode
from controller.lib.samba import (
    add_share,
    get_samba_status_dict,
    remove_share,
)

router = APIRouter(tags=["admin"])


# --- Hotspot ---

@router.get("/api/hotspot/status", response_model=HotspotStatusResponse)
async def hotspot_status() -> HotspotStatusResponse:
    """Get WiFi hotspot status."""
    return HotspotStatusResponse(**get_hotspot_status_dict())


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
