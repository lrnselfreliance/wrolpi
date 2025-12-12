"""
Status API endpoints for WROLPi Controller.

The main /api/status endpoint returns a format compatible with the
main WROLPi API so the React app can seamlessly use either source.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

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
    """
    Get full system status.

    Returns the same format as the main WROLPi API /api/status endpoint
    so the React Status.js component can use it directly.
    """
    return JSONResponse(content=get_full_status())


@router.get("/cpu")
async def get_cpu():
    """Get CPU status (usage, frequency, temperature)."""
    return JSONResponse(content=get_cpu_status())


@router.get("/memory")
async def get_memory():
    """Get memory usage statistics."""
    return JSONResponse(content=get_memory_status())


@router.get("/load")
async def get_load():
    """Get system load averages."""
    return JSONResponse(content=get_load_status())


@router.get("/drives")
async def get_drives():
    """Get disk usage for all mounted drives."""
    return JSONResponse(content=get_drive_status())


@router.get("/drives/primary")
async def get_primary_drive():
    """Get status of the primary WROLPi drive."""
    status = get_primary_drive_status()
    if status is None:
        return JSONResponse(content={"mounted": False})
    return JSONResponse(content={"mounted": True, **status})


@router.get("/network")
async def get_network():
    """Get network interface statistics."""
    return JSONResponse(content=get_network_status())


@router.get("/power")
async def get_power():
    """Get power status (undervoltage, throttling)."""
    return JSONResponse(content=get_power_status())
