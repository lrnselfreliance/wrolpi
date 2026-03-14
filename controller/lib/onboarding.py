"""
Onboarding orchestration for fresh WROLPi setup.

Guides a user through selecting a primary drive, reading its config,
mounting all drives per the config, and running repair.
"""

import logging
from pathlib import Path



import yaml

from controller.lib.config import (
    get_config_value,
    get_media_directory,
    is_docker_mode,
    is_primary_drive_mounted,
    reload_config_from_drive,
    save_config,
    update_config,
)
from controller.lib.disks import get_block_devices, mount_drive, unmount_drive
from controller.lib.fstab import add_fstab_entry
from controller.lib.scripts import start_script

logger = logging.getLogger(__name__)

TEMP_MOUNT_PATH = "/media/wrolpi_temp_onboarding"

# System mountpoints that should never be candidates
EXCLUDED_MOUNTPOINTS = {"/", "/boot", "/boot/firmware"}

# Partition labels that should never be candidates (case-insensitive)
EXCLUDED_LABELS = {"efi", "efi system partition"}


def get_onboarding_candidates() -> list[dict]:
    """
    Get partitions that could be the primary WROLPi drive.

    Includes both unmounted drives and drives auto-mounted under /media/
    (e.g. /media/pi/ on Raspberry Pi). Excludes system mounts and drives
    already mounted at the WROLPi primary location.

    Returns:
        List of dicts with drive info (path, name, size, fstype, label, uuid, model, mountpoint).
    """
    devices = get_block_devices()
    candidates = []
    for d in devices:
        # Skip system mounts
        if d.mountpoint in EXCLUDED_MOUNTPOINTS:
            continue
        # Skip the WROLPi primary mount and temp onboarding mount
        if d.mountpoint and d.mountpoint.startswith("/media/wrolpi"):
            continue
        # Skip EFI system partitions
        if d.label and d.label.lower() in EXCLUDED_LABELS:
            continue
        candidates.append({
            "path": d.path,
            "name": d.name,
            "size": d.size,
            "fstype": d.fstype,
            "label": d.label,
            "uuid": d.uuid,
            "model": d.model,
            "mountpoint": d.mountpoint,
        })
    return candidates


def _get_current_mountpoint(device_path: str):
    """Get the current mountpoint of a device, or None if not mounted."""
    for d in get_block_devices():
        if d.path == device_path and d.mountpoint:
            return d.mountpoint
    return None


def _cleanup_temp_mount() -> None:
    """Clean up any stale temp mount at TEMP_MOUNT_PATH."""
    temp_path = Path(TEMP_MOUNT_PATH)
    if temp_path.is_mount():
        logger.info("Cleaning up stale temp mount at %s", TEMP_MOUNT_PATH)
        unmount_drive(TEMP_MOUNT_PATH, lazy=True)
    if temp_path.exists():
        try:
            temp_path.rmdir()
        except OSError:
            pass


def probe_drive(device_path: str, fstype: str) -> dict:
    """
    Temp-mount a drive and check for WROLPi configuration.

    Leaves the drive temp-mounted so commit_onboarding can proceed quickly.

    Args:
        device_path: Device path (e.g. /dev/sda1)
        fstype: Filesystem type

    Returns:
        dict with config_found, mounts (from config), device_path, fstype, error
    """
    _cleanup_temp_mount()

    # If the drive is already mounted somewhere (e.g. auto-mounted on RPi),
    # unmount it first so we can temp-mount it ourselves.
    original_mountpoint = _get_current_mountpoint(device_path)
    if original_mountpoint:
        logger.info("Unmounting auto-mounted drive %s from %s", device_path, original_mountpoint)
        unmount_result = unmount_drive(original_mountpoint, lazy=True)
        if not unmount_result.get("success"):
            return {
                "success": False,
                "error": f"Failed to unmount {original_mountpoint}: {unmount_result.get('error')}",
                "config_found": False,
                "mounts": [],
                "device_path": device_path,
                "fstype": fstype,
            }

    result = mount_drive(device_path, TEMP_MOUNT_PATH, fstype=fstype)
    if not result.get("success"):
        return {
            "success": False,
            "error": result.get("error", "Failed to temp-mount drive"),
            "config_found": False,
            "mounts": [],
            "device_path": device_path,
            "fstype": fstype,
        }

    config_dir = Path(TEMP_MOUNT_PATH) / "config"
    controller_config = config_dir / "controller.yaml"
    wrolpi_config = config_dir / "wrolpi.yaml"
    # A WROLPi drive may have controller.yaml (new) or wrolpi.yaml (legacy)
    config_found = controller_config.exists() or wrolpi_config.exists()
    mounts = []

    if controller_config.exists():
        try:
            with open(controller_config) as f:
                config_data = yaml.safe_load(f) or {}
            mounts = config_data.get("drives", {}).get("mounts", [])
        except (IOError, yaml.YAMLError) as e:
            logger.warning("Failed to read config from temp mount: %s", e)

    return {
        "success": True,
        "config_found": config_found,
        "mounts": mounts,
        "device_path": device_path,
        "fstype": fstype,
    }


def cancel_probe() -> dict:
    """Unmount temp mount so user can pick a different drive."""
    _cleanup_temp_mount()
    return {"success": True}


def commit_onboarding(device_path: str, fstype: str, force: bool = False) -> dict:
    """
    Execute the full onboarding setup.

    1. Unmount temp mount
    2. Mount primary drive at /media/wrolpi
    3. Add fstab entry for primary
    4. Reload config
    5. Mount secondary drives per config
    6. Add fstab entries for secondary drives
    7. Start repair

    Args:
        device_path: Device path
        fstype: Filesystem type
        force: If True, proceed even without config on drive

    Returns:
        dict with success, error, mounts, repair_started
    """
    media_dir = str(get_media_directory())
    mounted_mounts = []

    try:
        # Step 1: Unmount temp mount if present
        _cleanup_temp_mount()

        # Step 1b: Clean up any transient config directory created on the root
        # filesystem (e.g. by generate_certificates.sh running before the drive
        # was mounted). This prevents stale root CAs from lingering.
        transient_config = Path(media_dir) / "config"
        if transient_config.exists() and not Path(media_dir).is_mount():
            import shutil
            shutil.rmtree(transient_config)
            logger.info("Removed transient config directory at %s", transient_config)

        # Step 2: Mount primary drive
        result = mount_drive(device_path, media_dir, fstype=fstype)
        if not result.get("success"):
            return {
                "success": False,
                "error": f"Failed to mount primary drive: {result.get('error')}",
                "mounts": [],
                "repair_started": False,
            }
        mounted_mounts.append(media_dir)

        # Step 3: Ensure config directory exists
        config_dir = Path(media_dir) / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Step 4: Add fstab entry for primary drive
        fstab_result = add_fstab_entry(device_path, media_dir, fstype)
        if not fstab_result.get("success"):
            logger.warning("Failed to add primary fstab entry: %s", fstab_result.get("error"))

        # Step 5: Reload config from drive and ensure controller.yaml exists
        reload_config_from_drive()
        try:
            save_config()
        except RuntimeError:
            pass

        # Step 5b: If config has no mounts, save the primary drive to config
        current_mounts = get_config_value("drives.mounts", [])
        if not current_mounts and fstab_result.get("success"):
            mount_entry = {
                "device": fstab_result.get("device", device_path),
                "mount_point": media_dir,
                "fstype": fstype,
                "options": "defaults",
            }
            update_config("drives.mounts", [mount_entry])
            try:
                save_config()
            except RuntimeError:
                pass

        # Step 6: Mount secondary drives per config
        config_path = Path(media_dir) / "config" / "controller.yaml"
        secondary_mounts = []
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config_data = yaml.safe_load(f) or {}
                secondary_mounts = config_data.get("drives", {}).get("mounts", [])
            except (IOError, yaml.YAMLError) as e:
                logger.warning("Failed to read config for secondary mounts: %s", e)

        for mount_entry in secondary_mounts:
            mount_point = mount_entry.get("mount_point")
            mount_device = mount_entry.get("device")
            mount_fstype = mount_entry.get("fstype", "auto")
            mount_options = mount_entry.get("options", "defaults")

            # Skip the primary mount (already mounted)
            if mount_point == media_dir:
                continue

            if not mount_device or not mount_point:
                continue

            mount_result = mount_drive(mount_device, mount_point, fstype=mount_fstype, options=mount_options)
            if mount_result.get("success"):
                mounted_mounts.append(mount_point)
                # Add fstab entry
                add_fstab_entry(mount_device, mount_point, mount_fstype, options=mount_options)
            else:
                logger.warning(
                    "Failed to mount secondary drive %s at %s: %s",
                    mount_device, mount_point, mount_result.get("error"),
                )

        # Step 7: Start repair
        repair_started = False
        repair_result = start_script("repair")
        if repair_result.get("success"):
            repair_started = True
        else:
            logger.warning("Failed to start repair: %s", repair_result.get("error"))

        return {
            "success": True,
            "mounts": mounted_mounts,
            "repair_started": repair_started,
        }

    except Exception as e:
        logger.exception("Onboarding failed")
        return {
            "success": False,
            "error": str(e),
            "mounts": mounted_mounts,
            "repair_started": False,
        }
