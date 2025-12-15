"""
fstab management for WROLPi Controller.

Provides persistent mount configuration via /etc/fstab.
"""

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from controller.lib.disks import get_uuid, validate_mount_point
from controller.lib.wrol_mode import require_normal_mode

FSTAB_PATH = Path("/etc/fstab")


def backup_fstab() -> Path:
    """Create a timestamped backup of fstab."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = Path(f"/etc/fstab.backup.{timestamp}")
    shutil.copy(FSTAB_PATH, backup_path)

    # Also keep a known backup location for easy recovery
    shutil.copy(FSTAB_PATH, Path("/etc/fstab.wrolpi.backup"))

    return backup_path


def parse_fstab() -> list[dict]:
    """Parse fstab into a list of entries."""
    entries = []

    with open(FSTAB_PATH, "r") as f:
        for line_num, line in enumerate(f, 1):
            stripped = line.strip()

            # Preserve comments and blank lines
            if not stripped or stripped.startswith("#"):
                entries.append({
                    "type": "comment",
                    "line": line,
                    "line_num": line_num,
                })
                continue

            parts = stripped.split()
            if len(parts) >= 4:
                entries.append({
                    "type": "mount",
                    "device": parts[0],
                    "mount_point": parts[1],
                    "fstype": parts[2],
                    "options": parts[3],
                    "dump": parts[4] if len(parts) > 4 else "0",
                    "pass": parts[5] if len(parts) > 5 else "0",
                    "line_num": line_num,
                })

    return entries


def _filter_entry_with_comment(entries: list[dict], mount_point: str) -> list[dict]:
    """
    Remove a mount entry and its preceding WROLPi comment if present.

    Args:
        entries: List of parsed fstab entries
        mount_point: Mount point to remove

    Returns:
        Filtered list without the mount entry and its associated WROLPi comment
    """
    result = []
    skip_indices = set()

    # First pass: identify which entries to skip
    for i, entry in enumerate(entries):
        if entry.get("mount_point") == mount_point:
            skip_indices.add(i)
            # Check if previous entry is a WROLPi comment
            if i > 0:
                prev_entry = entries[i - 1]
                if (prev_entry["type"] == "comment" and
                        "WROLPi managed mount" in prev_entry.get("line", "")):
                    skip_indices.add(i - 1)

    # Second pass: build result without skipped entries
    for i, entry in enumerate(entries):
        if i not in skip_indices:
            result.append(entry)

    return result


def add_fstab_entry(
        device: str,
        mount_point: str,
        fstype: str,
        options: str = "defaults,nofail,x-systemd.device-timeout=10s",
        use_uuid: bool = True,
) -> dict:
    """
    Add or update an fstab entry for persistent mounting.

    Args:
        device: Device path (will be converted to UUID if use_uuid=True)
        mount_point: Where to mount
        fstype: Filesystem type
        options: Mount options
        use_uuid: Convert device to UUID (recommended)

    Returns:
        dict with success status
    """
    # WROL Mode check
    try:
        require_normal_mode("add fstab entry")
    except PermissionError as e:
        return {"success": False, "error": str(e)}

    # Validate mount point
    try:
        validate_mount_point(mount_point)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    # Convert to UUID if requested
    if use_uuid and device.startswith("/dev/"):
        uuid = get_uuid(device)
        if uuid:
            device_spec = f"UUID={uuid}"
        else:
            device_spec = device
    else:
        device_spec = device

    # Backup fstab
    backup_fstab()

    # Read current fstab
    entries = parse_fstab()

    # Remove any existing entry for this mount point (and its WROLPi comment)
    entries = _filter_entry_with_comment(entries, mount_point)

    # Build new entry line
    new_entry = f"{device_spec} {mount_point} {fstype} {options} 0 2\n"

    # Write updated fstab
    with open(FSTAB_PATH, "w") as f:
        for entry in entries:
            if entry["type"] == "comment":
                f.write(entry["line"])
            else:
                f.write(
                    f"{entry['device']} {entry['mount_point']} {entry['fstype']} "
                    f"{entry['options']} {entry['dump']} {entry['pass']}\n"
                )
        # Add new entry with comment
        f.write(f"# WROLPi managed mount - added {datetime.now().isoformat()}\n")
        f.write(new_entry)

    # Reload systemd
    subprocess.run(["systemctl", "daemon-reload"], capture_output=True)

    return {
        "success": True,
        "device": device_spec,
        "mount_point": mount_point,
    }


def remove_fstab_entry(mount_point: str) -> dict:
    """
    Remove an fstab entry by mount point.

    Args:
        mount_point: Mount point to remove

    Returns:
        dict with success status
    """
    # WROL Mode check
    try:
        require_normal_mode("remove fstab entry")
    except PermissionError as e:
        return {"success": False, "error": str(e)}

    # Validate mount point
    try:
        validate_mount_point(mount_point)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    # Backup fstab
    backup_fstab()

    entries = parse_fstab()
    original_count = len([e for e in entries if e["type"] == "mount"])

    # Remove entry (and its WROLPi comment)
    entries = _filter_entry_with_comment(entries, mount_point)
    new_count = len([e for e in entries if e["type"] == "mount"])

    if original_count == new_count:
        return {"success": False, "error": f"No entry found for {mount_point}"}

    # Write updated fstab
    with open(FSTAB_PATH, "w") as f:
        for entry in entries:
            if entry["type"] == "comment":
                f.write(entry["line"])
            else:
                f.write(
                    f"{entry['device']} {entry['mount_point']} {entry['fstype']} "
                    f"{entry['options']} {entry['dump']} {entry['pass']}\n"
                )

    subprocess.run(["systemctl", "daemon-reload"], capture_output=True)

    return {"success": True, "mount_point": mount_point}


def get_wrolpi_fstab_entries() -> list[dict]:
    """Get all fstab entries for mounts under /media (WROLPi-managed mounts)."""
    entries = parse_fstab()
    return [
        e for e in entries
        if e["type"] == "mount" and e["mount_point"].startswith("/media")
    ]
