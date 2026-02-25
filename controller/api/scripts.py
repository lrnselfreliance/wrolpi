"""
Scripts API endpoints for WROLPi Controller.

Provides endpoints for running and monitoring maintenance scripts.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException

from controller.api.schemas import (
    BranchResponse,
    ScriptInfo,
    ScriptOutputResponse,
    ScriptStartRequest,
    ScriptStartResponse,
    ScriptStatusResponse,
)
from controller.lib.config import is_docker_mode
from controller.lib.scripts import (
    get_current_branch,
    get_script_output,
    get_script_status,
    list_available_scripts,
    start_script,
)

router = APIRouter(tags=["scripts"])


@router.get("/api/scripts", response_model=list[ScriptInfo])
async def scripts_list() -> list[ScriptInfo]:
    """List all available maintenance scripts."""
    scripts = list_available_scripts()
    return [ScriptInfo(**s) for s in scripts]


@router.get("/api/scripts/status", response_model=ScriptStatusResponse)
async def scripts_status() -> ScriptStatusResponse:
    """Get the status of any running script."""
    status = get_script_status()
    return ScriptStatusResponse(**status)


@router.get("/api/scripts/branch", response_model=BranchResponse)
async def scripts_branch() -> BranchResponse:
    """Get the current git branch of /opt/wrolpi."""
    if is_docker_mode():
        raise HTTPException(
            status_code=501,
            detail="Branch info not available in Docker mode"
        )

    branch = get_current_branch()
    return BranchResponse(branch=branch)


@router.post("/api/scripts/{name}/start", response_model=ScriptStartResponse)
async def scripts_start(
    name: str,
    request: Optional[ScriptStartRequest] = None,
) -> ScriptStartResponse:
    """Start a maintenance script."""
    if is_docker_mode():
        raise HTTPException(
            status_code=501,
            detail="Scripts are not available in Docker mode"
        )

    params = request.params if request else None
    result = start_script(name, params=params)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))

    return ScriptStartResponse(**result)


@router.get("/api/scripts/{name}/output", response_model=ScriptOutputResponse)
async def scripts_output(name: str, lines: int = 100) -> ScriptOutputResponse:
    """Get output from a script's log."""
    if is_docker_mode():
        raise HTTPException(
            status_code=501,
            detail="Scripts are not available in Docker mode"
        )

    # Limit lines to prevent abuse
    lines = min(max(1, lines), 5000)
    result = get_script_output(name, lines)
    return ScriptOutputResponse(**result)
