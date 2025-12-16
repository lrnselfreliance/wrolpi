"""
Disk management API endpoints for WROLPi Controller.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from controller.lib.config import (
    get_config_value,
    is_docker_mode,
    save_config,
    update_config,
)
from controller.lib.disks import (
    get_block_devices,
    get_mounts,
    mount_drive,
    unmount_drive,
)
from controller.lib.fstab import (
    add_fstab_entry,
    get_wrolpi_fstab_entries,
    remove_fstab_entry,
)
from controller.lib.smart import (
    get_all_smart_status,
    is_smart_available,
)

router = APIRouter(prefix="/api/disks", tags=["disks"])


class MountRequest(BaseModel):
    """Request model for mounting a drive."""
    device: str = Field(description="Device path (e.g., /dev/sda1)")
    mount_point: str = Field(description="Where to mount (must be under /media)")
    fstype: Optional[str] = Field(default=None, description="Filesystem type (auto-detected if not specified)")
    options: str = Field(default="defaults", description="Mount options")
    persist: bool = Field(default=False, description="Add to fstab for persistent mounting")


class UnmountRequest(BaseModel):
    """Request model for unmounting a drive."""
    mount_point: str = Field(description="Mount point to unmount")
    lazy: bool = Field(default=False, description="Use lazy unmount if busy")


class FstabRequest(BaseModel):
    """Request model for adding an fstab entry."""
    device: str = Field(description="Device path")
    mount_point: str = Field(description="Where to mount")
    fstype: str = Field(description="Filesystem type")
    options: str = Field(default="defaults,nofail,x-systemd.device-timeout=10s", description="Mount options")


def _check_native_mode():
    """Raise 501 if in Docker mode."""
    if is_docker_mode():
        raise HTTPException(
            status_code=501,
            detail="Disk management is not available in Docker mode. "
                   "Configure mounts on the host system."
        )


@router.get("")
async def list_disks():
    """List all detected disks/partitions."""
    _check_native_mode()

    devices = get_block_devices()
    return [
        {
            "name": d.name,
            "path": d.path,
            "size": d.size,
            "fstype": d.fstype,
            "mountpoint": d.mountpoint,
            "label": d.label,
            "uuid": d.uuid,
            "model": d.model,
        }
        for d in devices
    ]


@router.get("/mounts")
async def list_mounts():
    """List current mounts under /media."""
    _check_native_mode()
    return get_mounts()


@router.post("/mount")
async def disk_mount(request: MountRequest):
    """Mount a partition."""
    _check_native_mode()

    result = mount_drive(
        device=request.device,
        mount_point=request.mount_point,
        fstype=request.fstype,
        options=request.options,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Mount failed"))

    # Add to fstab if requested
    if request.persist:
        fstab_result = add_fstab_entry(
            device=request.device,
            mount_point=request.mount_point,
            fstype=request.fstype or "auto",
        )
        result["fstab"] = fstab_result

        # Save to controller.yaml to track WROLPi-managed mounts
        if fstab_result.get("success"):
            mount_entry = {
                "device": fstab_result.get("device", request.device),
                "mount_point": request.mount_point,
                "fstype": request.fstype or "auto",
                "options": request.options,
            }

            # Get current mounts, filter out any existing entry for same mount_point or device
            current_mounts = get_config_value("drives.mounts", [])
            current_mounts = [
                m for m in current_mounts
                if m.get("mount_point") != request.mount_point
                and m.get("device") != mount_entry["device"]
            ]
            current_mounts.append(mount_entry)

            update_config("drives.mounts", current_mounts)
            try:
                save_config()
            except RuntimeError:
                pass  # Primary drive not mounted - can't save yet

    return result


@router.post("/unmount")
async def disk_unmount(request: UnmountRequest):
    """Unmount a partition."""
    _check_native_mode()

    result = unmount_drive(
        mount_point=request.mount_point,
        lazy=request.lazy,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Unmount failed"))

    return result


@router.get("/fstab")
async def list_fstab():
    """Get WROLPi-related fstab entries."""
    _check_native_mode()
    return get_wrolpi_fstab_entries()


@router.post("/fstab")
async def add_fstab(request: FstabRequest):
    """Add an fstab entry for persistent mounting."""
    _check_native_mode()

    result = add_fstab_entry(
        device=request.device,
        mount_point=request.mount_point,
        fstype=request.fstype,
        options=request.options,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))

    return result


@router.delete("/fstab/{mount_point:path}")
async def delete_fstab(mount_point: str):
    """Remove an fstab entry."""
    _check_native_mode()

    # URL decode the mount point
    mount_point = f"/{mount_point}"

    result = remove_fstab_entry(mount_point)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))

    # Remove from controller.yaml - mount is no longer persistent
    current_mounts = get_config_value("drives.mounts", [])
    current_mounts = [m for m in current_mounts if m.get("mount_point") != mount_point]
    update_config("drives.mounts", current_mounts)
    try:
        save_config()
    except RuntimeError:
        pass  # Primary drive not mounted - can't save

    return result


# --- SMART ---

@router.get("/smart")
async def list_smart():
    """Get SMART status for all drives."""
    _check_native_mode()

    if not is_smart_available():
        return {"available": False, "reason": "pySMART not installed or not supported"}

    return {
        "available": True,
        "drives": get_all_smart_status(),
    }
