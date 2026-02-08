"""
Disk utilities for WROLPi Controller.

Provides disk detection, mounting, and WROLPi drive identification.
"""

import grp
import json
import pwd
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from controller.lib.config import get_config, is_docker_mode

SUPPORTED_FILESYSTEMS = {"ext4", "btrfs", "vfat", "exfat"}


def get_wrolpi_uid_gid() -> tuple[int, int]:
    """
    Get uid and gid for the wrolpi user.

    Returns:
        Tuple of (uid, gid). Falls back to (1001, 1001) if wrolpi user/group doesn't exist.
    """
    try:
        uid = pwd.getpwnam("wrolpi").pw_uid
        gid = grp.getgrnam("wrolpi").gr_gid
        return uid, gid
    except KeyError:
        return 1001, 1001  # wrolpi user is typically created after the first user


@dataclass
class BlockDevice:
    """Represents a block device/partition."""
    name: str
    path: str
    size: str
    fstype: Optional[str]
    mountpoint: Optional[str]
    label: Optional[str]
    uuid: Optional[str]
    model: Optional[str]
    is_wrolpi_drive: bool = False


def get_block_devices() -> list[BlockDevice]:
    """
    Get all block devices using lsblk.

    Returns:
        list of BlockDevice objects
    """
    if is_docker_mode():
        return []

    cmd = ["lsblk", "-J", "-o", "NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINT,LABEL,UUID,MODEL"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return []

        data = json.loads(result.stdout)
        devices = []

        def process_device(dev: dict, parent_model: str = None):
            if dev.get("type") == "part" and dev.get("fstype") in SUPPORTED_FILESYSTEMS:
                devices.append(BlockDevice(
                    name=dev["name"],
                    path=dev.get("path", f"/dev/{dev['name']}"),
                    size=dev.get("size", ""),
                    fstype=dev.get("fstype"),
                    mountpoint=dev.get("mountpoint"),
                    label=dev.get("label"),
                    uuid=dev.get("uuid"),
                    model=parent_model,
                ))
            # Process children (partitions)
            for child in dev.get("children", []):
                process_device(child, dev.get("model"))

        for device in data.get("blockdevices", []):
            process_device(device)

        return devices

    except (subprocess.SubprocessError, json.JSONDecodeError):
        return []


def get_uuid(device: str) -> Optional[str]:
    """
    Get UUID for a device using blkid.

    Args:
        device: Device path (e.g., /dev/sda1)

    Returns:
        UUID string or None
    """
    try:
        cmd = ["blkid", "-s", "UUID", "-o", "value", device]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except subprocess.SubprocessError:
        pass
    return None


def validate_mount_point(mount_point: str) -> None:
    """
    Validate that mount point is safe.

    Args:
        mount_point: Path to validate

    Raises:
        ValueError: If mount point is not allowed
    """
    import os

    if not mount_point.startswith("/media"):
        raise ValueError(
            f"Mount point must be under /media, got: {mount_point}. "
            "Mounting to other locations is not allowed."
        )

    # Prevent path traversal
    normalized = os.path.normpath(mount_point)
    if not normalized.startswith("/media"):
        raise ValueError(f"Invalid mount point after normalization: {normalized}")


def mount_drive(
        device: str,
        mount_point: str,
        fstype: Optional[str] = None,
        options: str = "defaults",
) -> dict:
    """
    Mount a drive.

    Args:
        device: Device path or UUID
        mount_point: Where to mount
        fstype: Filesystem type (auto-detected if not specified)
        options: Mount options

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    # Validate mount point
    try:
        validate_mount_point(mount_point)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    # Create mount point if needed
    Path(mount_point).mkdir(parents=True, exist_ok=True)

    # For exfat/vfat, add uid/gid options to set ownership to wrolpi user
    # These filesystems don't support POSIX permissions natively
    if fstype in ("exfat", "vfat"):
        uid, gid = get_wrolpi_uid_gid()
        options = f"{options},uid={uid},gid={gid}"

    # Build mount command
    cmd = ["mount"]
    if fstype:
        cmd.extend(["-t", fstype])
    if options:
        cmd.extend(["-o", options])
    cmd.extend([device, mount_point])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return {"success": True, "mount_point": mount_point}
        else:
            return {"success": False, "error": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Mount timed out"}


def unmount_drive(mount_point: str, lazy: bool = False) -> dict:
    """
    Unmount a drive with safety checks.

    Args:
        mount_point: Path to unmount
        lazy: Use lazy unmount if busy

    Returns:
        dict with success status
    """
    if is_docker_mode():
        return {"success": False, "error": "Not available in Docker mode"}

    # Safety rule: Don't unmount /media/wrolpi if no drives configured
    if mount_point == "/media/wrolpi":
        config = get_config()
        configured_mounts = config.get("drives", {}).get("mounts", [])

        if not configured_mounts:
            return {
                "success": False,
                "error": "Cannot unmount /media/wrolpi: No drives are configured. "
                         "This prevents accidental data loss.",
            }

        # Check if this is the primary drive
        primary_mount = next(
            (m for m in configured_mounts if m.get("is_primary")),
            None
        )
        if primary_mount:
            return {
                "success": False,
                "error": "Cannot unmount /media/wrolpi: This is the primary WROLPi drive.",
            }

    # Check if mount is busy
    if is_mount_busy(mount_point) and not lazy:
        return {
            "success": False,
            "error": f"Mount {mount_point} is busy. Use lazy unmount or stop services first.",
        }

    # Unmount
    cmd = ["umount"]
    if lazy:
        cmd.append("-l")
    cmd.append(mount_point)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return {"success": True, "mount_point": mount_point}
        else:
            return {"success": False, "error": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Unmount timed out"}


def is_mount_busy(mount_point: str) -> bool:
    """Check if any processes are using the mount point."""
    try:
        result = subprocess.run(
            ["lsof", "+D", mount_point],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def get_mounts() -> list[dict]:
    """
    Get current mounts under /media.

    Returns:
        list of mount info dicts
    """
    try:
        result = subprocess.run(
            ["findmnt", "-J", "-l", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []

        data = json.loads(result.stdout)
        mounts = []

        for fs in data.get("filesystems", []):
            target = fs.get("target", "")
            if target.startswith("/media"):
                mounts.append({
                    "mount_point": target,
                    "device": fs.get("source"),
                    "fstype": fs.get("fstype"),
                    "options": fs.get("options"),
                })

        return mounts
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return []
