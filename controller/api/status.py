"""
Stats API endpoints for WROLPi Controller.

Endpoints read from cached status data collected by the background worker.
Individual endpoints remain for backwards compatibility.
New aggregated /api/stats endpoint returns all status at once.

This endpoint provides system-level stats. App-level status (flags, downloads,
wrol_mode) remain in the main WROLPi API at /api/status.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from controller.lib.admin import get_hotspot_status, get_throttle_status, HotspotStatus
from controller.lib.config import is_docker_mode, is_rpi, is_rpi4, is_rpi5
from controller.lib.status import (
    get_cpu_status,
    get_load_status,
    get_memory_status,
    get_network_status,
    get_power_status,
    get_primary_drive_status,
)

router = APIRouter(prefix="/api/stats", tags=["stats"])


def get_cached_status(request: Request) -> dict:
    """Get cached status from app.state, or empty dict if not yet available."""
    return getattr(request.app.state, "cached_status", {})


def get_system_info() -> dict:
    """
    Get static system info that doesn't need frequent updates.
    These are collected on each request as they rarely change.
    """
    from controller.lib.config import get_config

    hotspot_status = get_hotspot_status()
    throttle_status = get_throttle_status()

    # Get hotspot SSID from config if hotspot is connected
    config = get_config()
    hotspot_config = config.get("hotspot", {})
    hotspot_ssid = hotspot_config.get("ssid", "WROLPi") if hotspot_status == HotspotStatus.connected else None

    return {
        "dockerized": is_docker_mode(),
        "is_rpi": is_rpi(),
        "is_rpi4": is_rpi4(),
        "is_rpi5": is_rpi5(),
        "hotspot_status": hotspot_status.name,
        "hotspot_ssid": hotspot_ssid,
        "throttle_status": throttle_status.name,
    }


@router.get("")
@router.get("/")
async def get_all_stats(request: Request):
    """
    Get all system status at once (cached data + system info).

    Returns aggregated CPU, memory, load, drives, network, power, iostat,
    processes, disk_bandwidth stats along with system info (dockerized,
    is_rpi, hotspot, throttle).

    This endpoint returns O(1) cached data updated every ~5 seconds,
    plus system info collected on each request.
    """
    cached = get_cached_status(request)

    if not cached:
        # Fallback to on-demand collection if cache not yet populated
        from controller.lib.status_worker import collect_all_status
        cached = await collect_all_status()

    # Add system info to response
    response = {**cached, **get_system_info()}
    return JSONResponse(content=response)


@router.get("/cpu")
async def get_cpu(request: Request):
    """Get CPU status (usage, frequency, temperature)."""
    cached = get_cached_status(request)
    if cached and cached.get("cpu_stats"):
        return JSONResponse(content=cached["cpu_stats"])
    return JSONResponse(content=get_cpu_status())


@router.get("/memory")
async def get_memory(request: Request):
    """Get memory usage statistics."""
    cached = get_cached_status(request)
    if cached and cached.get("memory_stats"):
        return JSONResponse(content=cached["memory_stats"])
    return JSONResponse(content=get_memory_status())


@router.get("/load")
async def get_load(request: Request):
    """Get system load averages."""
    cached = get_cached_status(request)
    if cached and cached.get("load_stats"):
        return JSONResponse(content=cached["load_stats"])
    return JSONResponse(content=get_load_status())


@router.get("/drives/primary")
async def get_primary_drive(request: Request):
    """Get status of the primary WROLPi drive."""
    cached = get_cached_status(request)
    if cached and cached.get("drives_stats"):
        # Find primary drive from cached drives
        for drive in cached["drives_stats"]:
            if drive.get("mount") == "/media/wrolpi":
                return JSONResponse(content={"mounted": True, **drive})
        return JSONResponse(content={"mounted": False})

    # Fallback to direct call
    status = get_primary_drive_status()
    if status is None:
        return JSONResponse(content={"mounted": False})
    return JSONResponse(content={"mounted": True, **status})


@router.get("/network")
async def get_network(request: Request):
    """Get network interface statistics."""
    cached = get_cached_status(request)
    if cached and cached.get("nic_bandwidth_stats"):
        return JSONResponse(content=cached["nic_bandwidth_stats"])
    return JSONResponse(content=get_network_status())


@router.get("/power")
async def get_power(request: Request):
    """Get power status (undervoltage, throttling)."""
    cached = get_cached_status(request)
    if cached and cached.get("power_stats"):
        return JSONResponse(content=cached["power_stats"])
    return JSONResponse(content=get_power_status())
