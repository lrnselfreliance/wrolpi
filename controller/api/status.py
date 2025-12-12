"""
Status API endpoints for WROLPi Controller.
"""

from fastapi import APIRouter

from controller.api.schemas import (
    CpuStatusResponse,
    DriveStatusResponse,
    FullStatusResponse,
    LoadStatusResponse,
    MemoryStatusResponse,
    NetworkInterfaceResponse,
    PowerStatusResponse,
    PrimaryDriveStatusResponse,
)
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


@router.get("", response_model=FullStatusResponse)
async def get_status() -> FullStatusResponse:
    """Get full system status."""
    return FullStatusResponse(**get_full_status())


@router.get("/cpu", response_model=CpuStatusResponse)
async def get_cpu() -> CpuStatusResponse:
    """Get CPU status (usage, frequency, temperature)."""
    return CpuStatusResponse(**get_cpu_status())


@router.get("/memory", response_model=MemoryStatusResponse)
async def get_memory() -> MemoryStatusResponse:
    """Get memory usage statistics."""
    return MemoryStatusResponse(**get_memory_status())


@router.get("/load", response_model=LoadStatusResponse)
async def get_load() -> LoadStatusResponse:
    """Get system load averages."""
    return LoadStatusResponse(**get_load_status())


@router.get("/drives", response_model=list[DriveStatusResponse])
async def get_drives() -> list[DriveStatusResponse]:
    """Get disk usage for all mounted drives."""
    return [DriveStatusResponse(**drive) for drive in get_drive_status()]


@router.get("/drives/primary", response_model=PrimaryDriveStatusResponse)
async def get_primary_drive() -> PrimaryDriveStatusResponse:
    """Get status of the primary WROLPi drive."""
    status = get_primary_drive_status()
    if status is None:
        return PrimaryDriveStatusResponse(mounted=False)
    return PrimaryDriveStatusResponse(mounted=True, **status)


@router.get("/network", response_model=list[NetworkInterfaceResponse])
async def get_network() -> list[NetworkInterfaceResponse]:
    """Get network interface statistics."""
    return [NetworkInterfaceResponse(**iface) for iface in get_network_status()]


@router.get("/power", response_model=PowerStatusResponse)
async def get_power() -> PowerStatusResponse:
    """Get power status (undervoltage, throttling)."""
    return PowerStatusResponse(**get_power_status())
