"""
Reconcile the live mount state under /media/ with fstab.yaml.

The Reconciler reads the desired mount table from fstab.yaml and asks an
injected MountExecutor what is currently mounted.  Then::

    mount    each entry in fstab.yaml that is missing from the live set
    unmount  each previously-managed path that has been removed from fstab.yaml

"Previously-managed" is the load-bearing concept: we never unmount paths
that WROLPi has never claimed.  The set of managed mount points is
persisted to ``managed_path`` (a small newline-separated file) so the
reconciler can tell apart its own mounts from the user's manual ones
across reboots.  On Portable this file is on tmpfs (overlay upper layer)
which is acceptable — each boot the reconciler starts from a clean managed
set and re-discovers everything from fstab.yaml.

The reconciler never raises for I/O failures.  Per-entry failures are
collected into the ReconcileResult and reported, but the run continues so
a single broken drive does not block the rest of the boot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from controller.lib.fstab_yaml import DEFAULT_PATH as DEFAULT_FSTAB_PATH
from controller.lib.fstab_yaml import FstabEntry, FstabFile, load as load_fstab
from controller.lib.mount_executor import MountExecutor

logger = logging.getLogger(__name__)

DEFAULT_MANAGED_PATH = Path("/run/wrolpi-mounts/managed")

# Mount points the reconciler will never touch, even if they appear in
# fstab.yaml: the primary mount belongs to live-boot persistence (Portable)
# or the host's installer (/etc/fstab on RPi/Debian), and the temp mount
# belongs to the Controller's onboarding flow.
RESERVED_MOUNT_POINTS = frozenset({
    "/media/wrolpi",
    "/media/wrolpi_temp_onboarding",
})


@dataclass
class ReconcileResult:
    """Per-run summary suitable for logging or surfacing back to an API."""

    mounted: list[str] = field(default_factory=list)
    unmounted: list[str] = field(default_factory=list)
    mount_failures: list[tuple[str, str]] = field(default_factory=list)
    unmount_failures: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    # Diagnostics: how many entries fstab.yaml listed, and which of them were
    # satisfied before this run.  Together with `skipped` these explain a
    # "nothing to do" reconcile in the journal.
    desired_count: int = 0
    already_mounted: list[str] = field(default_factory=list)

    @property
    def all_succeeded(self) -> bool:
        return not self.mount_failures and not self.unmount_failures


class Reconciler:
    """Apply fstab.yaml to the live mount state via an injected executor."""

    def __init__(
        self,
        *,
        executor: MountExecutor,
        fstab_path: Path = DEFAULT_FSTAB_PATH,
        managed_path: Path = DEFAULT_MANAGED_PATH,
        wrolpi_uid: Optional[int] = None,
        wrolpi_gid: Optional[int] = None,
    ):
        self._executor = executor
        self._fstab_path = fstab_path
        self._managed_path = managed_path
        self._wrolpi_uid = wrolpi_uid
        self._wrolpi_gid = wrolpi_gid

    # --- Public entry point ------------------------------------------

    def apply(self) -> ReconcileResult:
        """Reconcile once.  Idempotent."""
        result = ReconcileResult()

        desired = load_fstab(self._fstab_path)
        live = self._executor.current_mount_points()
        managed = self._read_managed()
        result.desired_count = len(desired.mounts)

        # 1. Mount each entry in fstab.yaml that isn't already live.
        for entry in desired.mounts:
            skip = self._skip_reason(entry)
            if skip:
                result.skipped.append((entry.mount_point, skip))
                continue
            if entry.mount_point in live:
                # Already mounted — claim ownership so a later removal can
                # safely unmount it.
                managed.add(entry.mount_point)
                result.already_mounted.append(entry.mount_point)
                continue
            options = self._inject_uid_gid(entry)
            self._ensure_dir(entry.mount_point)
            r = self._executor.mount(
                entry.device, entry.mount_point, entry.fstype, options,
            )
            if r.ok:
                result.mounted.append(entry.mount_point)
                managed.add(entry.mount_point)
            else:
                result.mount_failures.append((entry.mount_point, r.error or "unknown"))

        # 2. Unmount each previously-managed mount that is no longer in
        # fstab.yaml.  We only consider paths in the managed set, which
        # protects user-mounted /media/* paths the reconciler never owned.
        desired_set = desired.mount_points()
        for mp in sorted(managed - desired_set):
            if mp in RESERVED_MOUNT_POINTS:
                continue
            if mp not in live:
                managed.discard(mp)
                continue
            r = self._executor.unmount(mp)
            if r.ok:
                result.unmounted.append(mp)
                managed.discard(mp)
            else:
                result.unmount_failures.append((mp, r.error or "unknown"))

        self._write_managed(managed)
        return result

    # --- Internals -----------------------------------------------------

    def _skip_reason(self, entry: FstabEntry) -> Optional[str]:
        if not entry.device or not entry.mount_point:
            return "missing required field"
        if entry.mount_point in RESERVED_MOUNT_POINTS:
            return "reserved mount point"
        if not entry.mount_point.startswith("/media/"):
            return "mount point outside /media/"
        return None

    def _inject_uid_gid(self, entry: FstabEntry) -> str:
        """exfat/vfat/ntfs have no POSIX permissions; without uid/gid the
        mounted directory belongs to root and the wrolpi user cannot write
        to it.  Covers both NTFS drivers, matching mount_drive()."""
        options = entry.options or "defaults"
        if entry.fstype not in ("exfat", "vfat", "ntfs", "ntfs3"):
            return options
        if "uid=" in options or "gid=" in options:
            return options
        if self._wrolpi_uid is None or self._wrolpi_gid is None:
            return options
        return f"{options},uid={self._wrolpi_uid},gid={self._wrolpi_gid}"

    def _ensure_dir(self, mount_point: str) -> None:
        try:
            Path(mount_point).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("Could not create %s: %s", mount_point, e)

    def _read_managed(self) -> set[str]:
        if not self._managed_path.exists():
            return set()
        try:
            return {
                line.strip()
                for line in self._managed_path.read_text().splitlines()
                if line.strip()
            }
        except OSError as e:
            logger.warning("Could not read %s: %s", self._managed_path, e)
            return set()

    def _write_managed(self, managed: set[str]) -> None:
        try:
            self._managed_path.parent.mkdir(parents=True, exist_ok=True)
            self._managed_path.write_text(
                "\n".join(sorted(managed)) + ("\n" if managed else "")
            )
        except OSError as e:
            logger.warning("Could not write %s: %s", self._managed_path, e)
