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

The primary mount (the media directory) is also unmountable, to support
swapping in a backup drive: the wrolpi-api service is stopped first so
it releases open files, then the mount is released with a direct
umount(8).  See _unmount_primary().
"""

import logging
import os
import subprocess
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from controller.lib.config import get_media_directory, is_docker_mode
from controller.lib.fstab import add_fstab_entry as add_etc_fstab_entry
from controller.lib.fstab import parse_fstab as parse_etc_fstab
from controller.lib.fstab import remove_fstab_entry as remove_etc_fstab_entry
from controller.lib.disks import (
    check_shadowed_data,
    get_block_devices,
    get_mounts,
    get_uuid,
    mount_drive,
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
from controller.lib.systemd import stop_service
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

    if request.mount_point == str(get_media_directory()):
        # The primary mount is reserved: the reconciler never applies a
        # fstab.yaml entry for it.  Mount it directly and persist via the
        # host's /etc/fstab, as onboarding does.
        result = mount_drive(request.device, request.mount_point,
                             fstype=request.fstype,
                             options=request.options or "defaults")
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Failed to mount {request.mount_point}: {result.get('error')}")
        persisted = add_etc_fstab_entry(request.device, request.mount_point,
                                        request.fstype or "auto")
        if not persisted.get("success"):
            logger.warning("Mounted %s but could not persist to /etc/fstab: %s",
                           request.mount_point, persisted.get("error"))
        # Self-heal: drop any stale fstab.yaml entry for the primary mount
        # (written by older Controllers); the reconciler only ever skips it.
        data = load_fstab()
        if data.remove_by_mount_point(request.mount_point):
            save_fstab(data)
        return {
            "success": True,
            "device": persisted.get("device") or request.device,
            "mount_point": request.mount_point,
            "persisted": persisted.get("success", False),
        }

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


def _unmount_primary(normalized: str) -> dict:
    """Unmount the primary WROLPi drive (drive swap).

    The API service holds files open on the drive, so it is stopped first;
    a failed stop is not fatal — the umount result decides success.  The
    reconciler never manages the primary mount, so umount directly.  The
    /etc/fstab entry is left in place so a reboot restores the mount.
    """
    stopped = stop_service("wrolpi-api")
    if not stopped.get("success"):
        logger.warning("Could not stop wrolpi-api before unmounting %s: %s",
                       normalized, stopped.get("error"))

    if normalized in _executor.current_mount_points():
        result = _executor.unmount(normalized)
        if not result.ok:
            raise HTTPException(
                status_code=500,
                detail=f"{normalized} is still mounted: {result.error}",
            )

    return {
        "success": True,
        "mount_point": normalized,
        "removed_from_fstab": False,
        "stopped_services": ["wrolpi-api"] if stopped.get("success") else [],
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

    # The direct-umount paths below run as root, so be strict about what
    # we will pass to umount(8): a normalized path strictly under /media/.
    normalized = os.path.normpath(request.mount_point)
    if not normalized.startswith("/media/"):
        raise HTTPException(
            status_code=400,
            detail=f"Refusing to unmount {normalized}: not under /media/.",
        )
    if normalized == str(get_media_directory()):
        return _unmount_primary(normalized)
    if normalized in RESERVED_MOUNT_POINTS:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot unmount {request.mount_point}: it is a reserved "
                   f"mount point.",
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
    entries = [
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
        # Reserved mount points in fstab.yaml are never applied; hide them.
        if e.mount_point not in RESERVED_MOUNT_POINTS
    ]
    # The primary mount persists via the host's /etc/fstab (the reconciler
    # refuses to manage it) — include it so UIs can show its Persist state.
    media_dir = str(get_media_directory())
    try:
        for e in parse_etc_fstab():
            if e.get("type") == "mount" and e.get("mount_point") == media_dir:
                entries.append({
                    "type": "mount",
                    "device": e["device"],
                    "mount_point": e["mount_point"],
                    "fstype": e["fstype"],
                    "options": e["options"],
                    "dump": e.get("dump", "0"),
                    "pass": e.get("pass", "2"),
                })
    except OSError:
        pass
    return entries


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

    if request.mount_point == str(get_media_directory()):
        # The primary mount persists via the host's /etc/fstab; a fstab.yaml
        # entry would never be applied (RESERVED_MOUNT_POINTS).
        result = add_etc_fstab_entry(request.device, request.mount_point, request.fstype)
        if not result.get("success"):
            raise HTTPException(status_code=500,
                                detail=result.get("error") or "Failed to update /etc/fstab")
        # Self-heal: drop any stale fstab.yaml entry for the primary mount.
        data = load_fstab()
        if data.remove_by_mount_point(request.mount_point):
            save_fstab(data)
        return {"success": True, "device": result.get("device"),
                "mount_point": request.mount_point}

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

    if mount_point == str(get_media_directory()):
        result = remove_etc_fstab_entry(mount_point)
        # Also drop any stale fstab.yaml entry for the primary mount.
        data = load_fstab()
        removed_phantom = data.remove_by_mount_point(mount_point)
        if removed_phantom:
            save_fstab(data)
        if not result.get("success") and not removed_phantom:
            error = result.get("error") or f"No entry found for {mount_point}"
            status = 404 if "No entry found" in error else 500
            raise HTTPException(status_code=status, detail=error)
        return {"success": True, "mount_point": mount_point}

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
