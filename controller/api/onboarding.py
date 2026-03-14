"""
Onboarding API endpoints for WROLPi Controller.

Guides first-time setup: select drive, probe for config, mount, repair.
"""

from fastapi import APIRouter, HTTPException

from controller.api.schemas import (
    OnboardingCandidateResponse,
    OnboardingCommitRequest,
    OnboardingCommitResponse,
    OnboardingProbeRequest,
    OnboardingProbeResponse,
)
from controller.lib.config import is_docker_mode, is_primary_drive_mounted
from controller.lib.onboarding import (
    cancel_probe,
    commit_onboarding,
    get_onboarding_candidates,
    probe_drive,
)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


def _check_preconditions():
    """Check that onboarding is possible."""
    if is_docker_mode():
        raise HTTPException(
            status_code=501,
            detail="Onboarding is not available in Docker mode. "
                   "Configure mounts on the host system.",
        )
    if is_primary_drive_mounted():
        raise HTTPException(
            status_code=409,
            detail="Primary drive is already mounted. Onboarding is not needed.",
        )


@router.get("/candidates", response_model=list[OnboardingCandidateResponse])
async def list_candidates():
    """List available drives for onboarding."""
    _check_preconditions()
    candidates = get_onboarding_candidates()
    return [OnboardingCandidateResponse(**c) for c in candidates]


@router.post("/probe", response_model=OnboardingProbeResponse)
async def probe(request: OnboardingProbeRequest):
    """Temp-mount a drive and check for WROLPi configuration."""
    _check_preconditions()

    result = probe_drive(request.device_path, request.fstype)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Probe failed"))

    return OnboardingProbeResponse(
        config_found=result["config_found"],
        mounts=result["mounts"],
        device_path=result["device_path"],
        fstype=result["fstype"],
    )


@router.post("/commit", response_model=OnboardingCommitResponse)
async def commit(request: OnboardingCommitRequest):
    """Execute full onboarding: mount drives, add fstab entries, start repair."""
    if is_docker_mode():
        raise HTTPException(
            status_code=501,
            detail="Onboarding is not available in Docker mode.",
        )
    # Note: we don't check is_primary_drive_mounted here because commit
    # will mount it. The probe step already validated preconditions.

    result = commit_onboarding(
        device_path=request.device_path,
        fstype=request.fstype,
        force=request.force,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Onboarding failed"))

    return OnboardingCommitResponse(
        success=True,
        mounts=result.get("mounts", []),
        repair_started=result.get("repair_started", False),
    )


@router.post("/cancel")
async def cancel():
    """Cancel onboarding probe (unmount temp mount)."""
    if is_docker_mode():
        raise HTTPException(
            status_code=501,
            detail="Onboarding is not available in Docker mode.",
        )
    result = cancel_probe()
    return result
