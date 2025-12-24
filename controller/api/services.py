"""
Service management API endpoints for WROLPi Controller.
"""

from typing import Optional, Union

from fastapi import APIRouter, HTTPException, Query

from controller.api.schemas import (
    ServiceActionResponse,
    ServiceLogsResponse,
    ServiceStatusResponse,
    ServicesListErrorResponse,
)
from controller.lib.config import is_docker_mode
from controller.lib.docker_services import (
    can_manage_containers,
    get_all_containers_status,
    get_container_logs,
    get_container_status,
    restart_container,
    start_container,
    stop_container,
)
from controller.lib.systemd import (
    disable_service,
    enable_service,
    get_all_services_status,
    get_service_logs,
    get_service_status,
    restart_service,
    start_service,
    stop_service,
)

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get(
    "",
    response_model=Union[list[ServiceStatusResponse], ServicesListErrorResponse],
)
async def list_services() -> Union[list[ServiceStatusResponse], ServicesListErrorResponse]:
    """Get status of all managed services."""
    if is_docker_mode():
        if can_manage_containers():
            statuses = get_all_containers_status()
            statuses = sorted(statuses, key=lambda s: s["name"])
            return [ServiceStatusResponse(**s) for s in statuses if "error" not in s]
        else:
            return ServicesListErrorResponse(
                error="Docker management not available",
                reason="Docker socket not mounted or docker library not installed",
            )
    else:
        statuses = get_all_services_status()
        statuses = sorted(statuses, key=lambda s: s["name"])
        return [ServiceStatusResponse(**s) for s in statuses]


@router.get("/{name}", response_model=ServiceStatusResponse)
async def get_service(name: str) -> ServiceStatusResponse:
    """Get status of a specific service."""
    if is_docker_mode():
        status = get_container_status(name)
    else:
        status = get_service_status(name)

    if "error" in status and status.get("status") is None:
        raise HTTPException(status_code=404, detail=status["error"])

    return ServiceStatusResponse(**status)


@router.post("/{name}/start", response_model=ServiceActionResponse)
async def service_start(name: str) -> ServiceActionResponse:
    """Start a service."""
    if is_docker_mode():
        result = start_container(name)
    else:
        result = start_service(name)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to start"))

    return ServiceActionResponse(**result)


@router.post("/{name}/stop", response_model=ServiceActionResponse)
async def service_stop(name: str) -> ServiceActionResponse:
    """Stop a service."""
    if is_docker_mode():
        result = stop_container(name)
    else:
        result = stop_service(name)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to stop"))

    return ServiceActionResponse(**result)


@router.post("/{name}/restart", response_model=ServiceActionResponse)
async def service_restart(name: str) -> ServiceActionResponse:
    """Restart a service."""
    if is_docker_mode():
        result = restart_container(name)
    else:
        result = restart_service(name)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to restart"))

    return ServiceActionResponse(**result)


@router.post("/{name}/enable", response_model=ServiceActionResponse)
async def service_enable(name: str) -> ServiceActionResponse:
    """Enable a service to start at boot (systemd only)."""
    if is_docker_mode():
        raise HTTPException(
            status_code=501,
            detail="Enable/disable not available in Docker mode"
        )

    result = enable_service(name)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))

    return ServiceActionResponse(**result)


@router.post("/{name}/disable", response_model=ServiceActionResponse)
async def service_disable(name: str) -> ServiceActionResponse:
    """Disable a service from starting at boot (systemd only)."""
    if is_docker_mode():
        raise HTTPException(
            status_code=501,
            detail="Enable/disable not available in Docker mode"
        )

    result = disable_service(name)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))

    return ServiceActionResponse(**result)


@router.get("/{name}/logs", response_model=ServiceLogsResponse)
async def service_logs(
        name: str,
        lines: int = Query(default=100, ge=1, le=10000),
        since: Optional[str] = Query(default=None),
) -> ServiceLogsResponse:
    """Get service logs."""
    if is_docker_mode():
        result = get_container_logs(name, lines)
    else:
        result = get_service_logs(name, lines, since)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return ServiceLogsResponse(**result)
