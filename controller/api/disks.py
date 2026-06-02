"""
Disk management API endpoints for WROLPi Controller.

The Controller defines what should be mounted (writes fstab.yaml on the
WROLPi drive) but never calls mount(8) itself.  After every write to
fstab.yaml the Controller triggers wrolpi-mounts.service via
``systemctl restart``; the service reconciles live state to match.  The
Controller verifies the outcome by reading /proc/mounts through the same
MountExecutor abstraction the service uses.

One exception: the reconciler deliberately never unmounts paths it has
not claimed, so foreign mounts (udisks2 desktop automounts, manual
mounts) under /media/ would otherwise be impossible to remove from the
UI.  When a reconcile leaves the requested mount point live, /unmount
falls back to a direct umount(8) for non-reserved /media/ paths.
"""

import logging
import os
import subprocess
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from controller.lib.config import is_docker_mode
from controller.lib.disks import (
    check_shadowed_data,
    get_block_devices,
    get_mounts,
    get_uuid,
    validate_mount_point,
)
from controller.lib.fstab_yaml import (
    FstabEntry,
    load as load_fstab,
    save as save_fstab,
)
from controller.lib.mount_executor import (
    MountExecutor,
    SubprocessMountExecutor,
)
from controller.lib.reconciler import RESERVED_MOUNT_POINTS
from controller.lib.smart import (
    get_all_smart_status,
    is_smart_available,
)
from controller.lib.wrol_mode import require_normal_mode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/disks", tags=["disks"])

# Module-level executor — production uses the real subprocess-backed one.
# Tests rebind this attribute (and ``_trigger_reconcile``) via monkeypatch
# to inject a FakeMountExecutor without touching subprocess or /proc.
_executor: MountExecutor = SubprocessMountExecutor()

RECONCILE_TIMEOUT_SECONDS = 60


class MountRequest(BaseModel):
    """Request model for mounting a drive."""
    device: str = Field(description="Device path (e.g., /dev/sda1)")
    mount_point: str = Field(description="Where to mount (must be under /media)")
    fstype: Optional[str] = Field(default=None,
                                  description="Filesystem type (auto-detected if not specified)")
    options: str = Field(default="defaults", description="Mount options")
    # `persist` is accepted for API compatibility but no longer
    # meaningful: every Controller-initiated mount goes through fstab.yaml
    # and the Reconciler.  A future UI cleanup will remove the field.
    persist: bool = Field(default=True, description="(Deprecated; always persistent.)")
    force_shadowed: bool = Field(
        default=False,
        description="Proceed even if existing data at the mount target would be hidden by the new mount",
    )


class UnmountRequest(BaseModel):
    mount_point: str = Field(description="Mount point to unmount")
    lazy: bool = Field(default=False,
                       description="(Deprecated; reconciler chooses the strategy.)")


class FstabRequest(BaseModel):
    device: str = Field(description="Device path")
    mount_point: str = Field(description="Where to mount")
    fstype: str = Field(description="Filesystem type")
    options: str = Field(default="defaults",
                         description="Mount options")


def _check_native_mode():
    """Raise 501 if in Docker mode."""
    if is_docker_mode():
        raise HTTPException(
            status_code=501,
            detail="Disk management is not available in Docker mode. "
                   "Configure mounts on the host system."
        )


def _to_uuid_spec(device: str) -> str:
    """Convert a /dev/sdX path to UUID=... if possible; passthrough otherwise.

    Persistent mount entries must be UUID-keyed so they travel with the
    drive between hosts.  Already-formatted UUID=/PARTUUID=/LABEL= specs
    pass through unchanged.
    """
    if not device.startswith("/dev/"):
        return device
    uuid = get_uuid(device)
    return f"UUID={uuid}" if uuid else device


def _trigger_reconcile() -> tuple[bool, Optional[str]]:
    """Ask systemd to re-run wrolpi-mounts.service.  Blocks until the
    oneshot completes; returns (ok, error_or_none)."""
    cmd = ["systemctl", "restart", "wrolpi-mounts.service"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=RECONCILE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, f"systemctl restart wrolpi-mounts.service timed out " \
                      f"after {RECONCILE_TIMEOUT_SECONDS}s"
    if result.returncode != 0:
        return False, (result.stderr.strip()
                       or f"systemctl exit {result.returncode}")
    return True, None


# --- Read endpoints (no fstab.yaml mutation) ------------------------------

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


# --- Mount / unmount ------------------------------------------------------

@router.post("/mount")
async def disk_mount(request: MountRequest):
    """Add a mount to fstab.yaml and reconcile."""
    _check_native_mode()

    # Soft-block if the mount target already contains user data that would
    # be hidden by the new mount.  UI re-submits with force_shadowed=True
    # to override.
    if not request.force_shadowed:
        shadowed = check_shadowed_data(request.mount_point)
        if shadowed:
            return {
                "success": False,
                "needs_force": "shadowed",
                "shadowed_data": shadowed,
                "error": (
                    f"{request.mount_point} contains {len(shadowed['entries'])} "
                    f"existing data "
                    f"{'entry' if len(shadowed['entries']) == 1 else 'entries'}. "
                    f"Mounting now would hide them on the underlying filesystem."
                ),
            }

    try:
        require_normal_mode("mount")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        validate_mount_point(request.mount_point)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    device_spec = _to_uuid_spec(request.device)
    entry = FstabEntry(
        device=device_spec,
        mount_point=request.mount_point,
        fstype=request.fstype or "auto",
        options=request.options or "defaults",
    )

    data = load_fstab()
    data.add_or_replace(entry)
    save_fstab(data)

    ok, err = _trigger_reconcile()
    if not ok:
        raise HTTPException(status_code=500,
                            detail=f"Failed to reconcile mounts: {err}")

    if request.mount_point not in _executor.current_mount_points():
        # Entry is in fstab.yaml and will be retried on next reconcile, but
        # this attempt did not produce a live mount — surface the failure.
        raise HTTPException(
            status_code=500,
            detail=f"Reconciler ran but {request.mount_point} did not mount. "
                   f"Check journalctl -u wrolpi-mounts.service.",
        )

    return {
        "success": True,
        "device": device_spec,
        "mount_point": request.mount_point,
    }


@router.post("/unmount")
async def disk_unmount(request: UnmountRequest):
    """Remove a mount from fstab.yaml and reconcile.

    Falls back to a direct umount when the mount survives the reconcile —
    a foreign mount (udisks2 automount, manual mount) the reconciler never
    claimed, or a managed mount the reconciler could not release.
    """
    _check_native_mode()

    try:
        require_normal_mode("unmount")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        validate_mount_point(request.mount_point)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # The direct-umount fallback below runs as root, so be strict about
    # what we will pass to umount(8): a normalized path strictly under
    # /media/ that is not the primary drive.
    normalized = os.path.normpath(request.mount_point)
    if normalized in RESERVED_MOUNT_POINTS:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot unmount {request.mount_point}: it is the primary "
                   f"WROLPi drive.",
        )
    if not normalized.startswith("/media/"):
        raise HTTPException(
            status_code=400,
            detail=f"Refusing to unmount {normalized}: not under /media/.",
        )

    data = load_fstab()
    removed = data.remove_by_mount_point(request.mount_point)
    save_fstab(data)

    ok, err = _trigger_reconcile()
    if not ok:
        raise HTTPException(status_code=500,
                            detail=f"Failed to reconcile mounts: {err}")

    if normalized in _executor.current_mount_points():
        # The reconciler did not release it — either a foreign mount it
        # never claimed, or the umount failed.  Try directly.
        result = _executor.unmount(normalized)
        if not result.ok:
            raise HTTPException(
                status_code=500,
                detail=f"{normalized} is still mounted: {result.error}",
            )

    return {
        "success": True,
        "mount_point": request.mount_point,
        "removed_from_fstab": removed,
    }


# --- fstab.yaml read/write endpoints --------------------------------------

@router.get("/fstab")
async def list_fstab():
    """Return the WROLPi-managed mount table (fstab.yaml)."""
    _check_native_mode()
    data = load_fstab()
    return [
        {
            "type": "mount",
            "device": e.device,
            "mount_point": e.mount_point,
            "fstype": e.fstype,
            "options": e.options,
            "dump": "0",
            "pass": "2",
        }
        for e in data.mounts
    ]


@router.post("/fstab")
async def add_fstab(request: FstabRequest):
    """Add a row to fstab.yaml without triggering a reconcile.

    Use disk_mount() to add AND apply.  This endpoint is for callers that
    want to stage changes without immediately mounting.
    """
    _check_native_mode()

    try:
        require_normal_mode("add fstab entry")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        validate_mount_point(request.mount_point)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    device_spec = _to_uuid_spec(request.device)
    data = load_fstab()
    data.add_or_replace(FstabEntry(
        device=device_spec,
        mount_point=request.mount_point,
        fstype=request.fstype,
        options=request.options or "defaults",
    ))
    save_fstab(data)

    return {"success": True, "device": device_spec,
            "mount_point": request.mount_point}


@router.delete("/fstab/{mount_point:path}")
async def delete_fstab(mount_point: str):
    """Remove a row from fstab.yaml without triggering a reconcile."""
    _check_native_mode()

    # URL decode the mount point
    mount_point = f"/{mount_point}"

    try:
        require_normal_mode("remove fstab entry")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        validate_mount_point(mount_point)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    data = load_fstab()
    if not data.remove_by_mount_point(mount_point):
        raise HTTPException(status_code=404,
                            detail=f"No entry found for {mount_point}")
    save_fstab(data)
    return {"success": True, "mount_point": mount_point}


# --- SMART ---

@router.get("/smart")
async def list_smart():
    """Get SMART status for all drives."""
    _check_native_mode()

    if not is_smart_available():
        return {"available": False,
                "reason": "pySMART not installed or not supported"}

    return {
        "available": True,
        "drives": get_all_smart_status(),
    }
