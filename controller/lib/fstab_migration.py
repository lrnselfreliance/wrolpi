"""
One-time migration of WROLPi-managed mount entries into fstab.yaml.

Two legacy sources exist:

1. ``/etc/fstab`` — older WROLPi versions wrote WROLPi-managed mounts as
   ordinary fstab lines so systemd-fstab-generator would mount them at
   boot.  On Portable this is read-only squashfs (writes go to RAM and
   evaporate), and on any host an /etc/fstab entry is tied to *that* host,
   not the drive.

2. ``controller.yaml drives.mounts`` — a brief intermediate iteration
   stored the mount table alongside Controller settings in
   ``/media/wrolpi/config/controller.yaml``.  Lives on the drive but
   conflates "definitions" with "applier"; we split them out into a
   dedicated file.

Both sources feed into ``/media/wrolpi/config/fstab.yaml``.  Each source
is migrated at most once (gated by a marker file).  /etc/fstab is backed
up; migrated lines are commented in place rather than deleted so the host
admin can hand-recover if something goes wrong.
"""

import logging
import shutil
from pathlib import Path

import yaml

from controller.lib.fstab_yaml import (
    DEFAULT_PATH as DEFAULT_FSTAB_YAML_PATH,
    FstabEntry,
    load as load_fstab_yaml,
    save as save_fstab_yaml,
)

logger = logging.getLogger(__name__)

FSTAB_PATH = Path("/etc/fstab")
CONTROLLER_YAML_PATH = Path("/media/wrolpi/config/controller.yaml")
MARKER_PATH = Path("/media/wrolpi/config/.fstab-migrated")
BACKUP_PATH = Path("/etc/fstab.wrolpi-migration.backup")

# Mount points that legitimately appear in /etc/fstab or drives.mounts but
# must not be lifted into fstab.yaml: the primary's mount is host-specific
# (live-boot, /etc/fstab installer entry, or repair.sh sets it up directly)
# and the temp onboarding mount belongs to the Controller's onboarding flow.
EXCLUDED_MIGRATION_MOUNT_POINTS = frozenset({
    "/media/wrolpi",
    "/media/wrolpi_temp_onboarding",
})

MIGRATED_PREFIX = "# migrated to fstab.yaml:"


# --- /etc/fstab parser ----------------------------------------------------

def _parse_fstab_text(text: str) -> list[dict]:
    """Parse the contents of an fstab file into structured entries."""
    entries: list[dict] = []
    for raw in text.splitlines(keepends=False):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            entries.append({"type": "comment", "line": raw})
            continue
        parts = stripped.split()
        if len(parts) >= 4:
            entries.append({
                "type": "mount",
                "device": parts[0],
                "mount_point": parts[1],
                "fstype": parts[2],
                "options": parts[3],
                "line": raw,
            })
        else:
            entries.append({"type": "comment", "line": raw})
    return entries


def _is_migration_candidate(entry: dict) -> bool:
    if entry.get("type") != "mount":
        return False
    mp = entry.get("mount_point", "")
    if not mp.startswith("/media"):
        return False
    if mp in EXCLUDED_MIGRATION_MOUNT_POINTS:
        return False
    return True


# --- controller.yaml helpers ----------------------------------------------

def _read_controller_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        logger.warning("Could not parse %s, treating as empty: %s", path, e)
        return {}


def _save_controller_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=True))


# --- Main entry point -----------------------------------------------------

def migrate_etc_fstab(
    *,
    fstab_path: Path = FSTAB_PATH,
    controller_yaml_path: Path = CONTROLLER_YAML_PATH,
    fstab_yaml_path: Path = None,
    marker_path: Path = MARKER_PATH,
    backup_path: Path = BACKUP_PATH,
) -> dict:
    """Lift WROLPi-managed mounts from /etc/fstab and
    controller.yaml drives.mounts into fstab.yaml.

    Returns ``{migrated, reason?, count}`` where ``count`` is the number of
    new entries added to fstab.yaml.
    """
    if marker_path.exists():
        return {"migrated": False, "reason": "already-migrated", "count": 0}

    fstab_yaml_path = fstab_yaml_path or DEFAULT_FSTAB_YAML_PATH

    # --- Gather candidates from both sources ----------------------------
    etc_fstab_candidates: list[dict] = []
    if fstab_path.exists():
        try:
            etc_fstab_text = fstab_path.read_text()
        except OSError as e:
            logger.warning("Could not read %s: %s", fstab_path, e)
            etc_fstab_text = ""
        etc_fstab_entries = _parse_fstab_text(etc_fstab_text)
        etc_fstab_candidates = [
            e for e in etc_fstab_entries if _is_migration_candidate(e)
        ]
    else:
        etc_fstab_text = ""
        etc_fstab_entries = []

    controller_data = _read_controller_yaml(controller_yaml_path)
    drives_mounts_candidates = []
    for m in (controller_data.get("drives") or {}).get("mounts") or []:
        mp = m.get("mount_point", "")
        if not mp.startswith("/media") or mp in EXCLUDED_MIGRATION_MOUNT_POINTS:
            continue
        drives_mounts_candidates.append(m)

    # --- Backup /etc/fstab before any modification ----------------------
    if etc_fstab_candidates:
        try:
            shutil.copy2(fstab_path, backup_path)
        except OSError as e:
            logger.warning("Could not back up %s: %s", fstab_path, e)

    # --- Merge into fstab.yaml (dedup by mount_point) -------------------
    fstab_data = load_fstab_yaml(fstab_yaml_path)
    existing = fstab_data.mount_points()
    added = 0

    for cand in etc_fstab_candidates:
        if cand["mount_point"] in existing:
            continue
        fstab_data.add_or_replace(FstabEntry(
            device=cand["device"],
            mount_point=cand["mount_point"],
            fstype=cand["fstype"],
            options=cand.get("options") or "defaults",
        ))
        existing.add(cand["mount_point"])
        added += 1

    for cand in drives_mounts_candidates:
        mp = cand["mount_point"]
        if mp in existing:
            continue
        fstab_data.add_or_replace(FstabEntry(
            device=cand.get("device", ""),
            mount_point=mp,
            fstype=cand.get("fstype") or "auto",
            options=cand.get("options") or "defaults",
        ))
        existing.add(mp)
        added += 1

    if etc_fstab_candidates or drives_mounts_candidates:
        save_fstab_yaml(fstab_data, fstab_yaml_path)

    # --- Comment out migrated entries in /etc/fstab ---------------------
    if etc_fstab_candidates:
        candidate_mps = {e["mount_point"] for e in etc_fstab_candidates}
        new_lines = []
        for entry in etc_fstab_entries:
            if (entry["type"] == "mount"
                    and entry["mount_point"] in candidate_mps):
                new_lines.append(f"{MIGRATED_PREFIX} {entry['line']}")
            else:
                new_lines.append(entry["line"])
        suffix = "\n" if etc_fstab_text.endswith("\n") else ""
        try:
            fstab_path.write_text("\n".join(new_lines) + suffix)
        except OSError as e:
            logger.warning("Could not rewrite %s: %s", fstab_path, e)

    # --- Strip drives.mounts from controller.yaml -----------------------
    if drives_mounts_candidates and (controller_data.get("drives") or {}).get("mounts"):
        drives = controller_data.get("drives") or {}
        drives.pop("mounts", None)
        if not drives:
            controller_data.pop("drives", None)
        else:
            controller_data["drives"] = drives
        _save_controller_yaml(controller_yaml_path, controller_data)

    # --- Mark done ------------------------------------------------------
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.touch()

    logger.info(
        "Migration complete: %d /etc/fstab candidate(s), %d drives.mounts "
        "candidate(s), %d new entry/entries written to fstab.yaml",
        len(etc_fstab_candidates), len(drives_mounts_candidates), added,
    )
    return {"migrated": True, "count": added}
