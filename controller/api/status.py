"""
Status API endpoints for WROLPi Controller.
"""

from fastapi import APIRouter

from controller.lib.status import (
    get_cpu_status,
    get_drive_status,
    get_full_status,
    get_load_status,
    get_memory_status,
    get_network_status,
    get_power_status,
    get_primary_drive_status,
)


router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("")
async def get_status():
    """Get full system status."""
    return get_full_status()


@router.get("/cpu")
async def get_cpu():
    """Get CPU status (usage, frequency, temperature)."""
    return get_cpu_status()


@router.get("/memory")
async def get_memory():
    """Get memory usage statistics."""
    return get_memory_status()


@router.get("/load")
async def get_load():
    """Get system load averages."""
    return get_load_status()


@router.get("/drives")
async def get_drives():
    """Get disk usage for all mounted drives."""
    return get_drive_status()


@router.get("/drives/primary")
async def get_primary_drive():
    """Get status of the primary WROLPi drive."""
    status = get_primary_drive_status()
    if status is None:
        return {"mounted": False}
    return {"mounted": True, **status}


@router.get("/network")
async def get_network():
    """Get network interface statistics."""
    return get_network_status()


@router.get("/power")
async def get_power():
    """Get power status (undervoltage, throttling)."""
    return get_power_status()
