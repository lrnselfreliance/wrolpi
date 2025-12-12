"""
Admin API endpoints for WROLPi Controller.
"""

from fastapi import APIRouter, HTTPException

from controller.api.schemas import (
    HotspotActionResponse,
    HotspotStatusResponse,
    RestartServicesResponse,
    ServiceRestartResult,
    SystemActionResponse,
    ThrottleActionResponse,
    ThrottleStatusResponse,
)
from controller.lib.admin import (
    disable_hotspot,
    disable_throttle,
    enable_hotspot,
    enable_throttle,
    get_hotspot_status_dict,
    get_throttle_status_dict,
    reboot_system,
    restart_all_services,
    shutdown_system,
)
from controller.lib.config import is_docker_mode

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
