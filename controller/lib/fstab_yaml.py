"""
Reader/writer for /media/wrolpi/config/fstab.yaml.

This file is the WROLPi-managed mount table.  It lives on the drive itself
(so it travels between hosts) and is the sole input to the Reconciler.

Schema::

    version: 1
    mounts:
      - device: UUID=...           # filesystem UUID; the entry is portable
        mount_point: /media/...    # must be under /media
        fstype: ext4
        options: defaults          # mount(8) -o options

The Controller defines what should be mounted by editing this file; the
Reconciler (invoked by wrolpi-mounts.service) applies the diff between this
file and the live mount state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path("/media/wrolpi/config/fstab.yaml")
SCHEMA_VERSION = 1


@dataclass
class FstabEntry:
    """A single row in fstab.yaml."""

    device: str
    mount_point: str
    fstype: str
    options: str = "defaults"

    def to_dict(self) -> dict:
        return {
            "device": self.device,
            "mount_point": self.mount_point,
            "fstype": self.fstype,
            "options": self.options,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FstabEntry":
        return cls(
            device=data.get("device", ""),
            mount_point=data.get("mount_point", ""),
            fstype=data.get("fstype", "auto"),
            options=data.get("options") or "defaults",
        )


@dataclass
class FstabFile:
    """In-memory representation of fstab.yaml."""

    version: int = SCHEMA_VERSION
    mounts: list[FstabEntry] = field(default_factory=list)

    # --- Lookup helpers ------------------------------------------------

    def find_by_mount_point(self, mount_point: str) -> Optional[FstabEntry]:
        for m in self.mounts:
            if m.mount_point == mount_point:
                return m
        return None

    def mount_points(self) -> set[str]:
        return {m.mount_point for m in self.mounts}

    # --- Mutation -------------------------------------------------------

    def add_or_replace(self, entry: FstabEntry) -> None:
        """Insert ``entry``, replacing any prior row that shares its
        mount_point OR its device.  The device clause handles the "remount
        the same drive to a different path" case so we don't accumulate
        stale rows."""
        self.mounts = [
            m for m in self.mounts
            if m.mount_point != entry.mount_point and m.device != entry.device
        ]
        self.mounts.append(entry)

    def remove_by_mount_point(self, mount_point: str) -> bool:
        """Remove the entry at ``mount_point``.  Returns True if a row was
        removed, False if none matched."""
        before = len(self.mounts)
        self.mounts = [m for m in self.mounts if m.mount_point != mount_point]
        return len(self.mounts) < before


# --- File I/O -------------------------------------------------------------

def load(path: Optional[Path] = None) -> FstabFile:
    """Read fstab.yaml.  Returns an empty FstabFile if the file is absent
    or malformed; both are normal startup conditions on a fresh drive.

    ``path`` defaults to the module-level ``DEFAULT_PATH`` at call time
    (resolved on each invocation, so tests can redirect via monkeypatch).
    """
    if path is None:
        path = DEFAULT_PATH
    if not path.exists():
        return FstabFile()
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        logger.warning("fstab.yaml at %s is malformed (%s); treating as empty", path, e)
        return FstabFile()
    version = raw.get("version", SCHEMA_VERSION)
    mounts = [FstabEntry.from_dict(m) for m in (raw.get("mounts") or [])]
    return FstabFile(version=version, mounts=mounts)


def save(data: FstabFile, path: Optional[Path] = None) -> None:
    """Write fstab.yaml atomically (write-then-rename).  Creates the parent
    directory if needed.  Sorted by mount_point so diffs stay tidy.

    ``path`` defaults to the module-level ``DEFAULT_PATH`` at call time so
    tests can redirect via monkeypatch.
    """
    if path is None:
        path = DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_mounts = sorted(data.mounts, key=lambda m: m.mount_point)
    serialised = yaml.safe_dump(
        {
            "version": data.version,
            "mounts": [m.to_dict() for m in sorted_mounts],
        },
        default_flow_style=False,
        sort_keys=True,
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(serialised)
    tmp.replace(path)
