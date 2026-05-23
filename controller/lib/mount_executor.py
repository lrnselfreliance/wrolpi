"""
The narrow interface between WROLPi's mount reconciler and the operating
system.  Pulling these three operations behind a single abstraction lets the
reconciler stay pure-orchestration: tests construct a FakeMountExecutor that
records calls + holds an in-memory mount-table, with no patches against
subprocess, /proc/mounts, or pwd/grp.

Two implementations live here:

- SubprocessMountExecutor — production.  Calls mount(8) / umount(8) via
  subprocess and reads /proc/mounts.

- FakeMountExecutor — tests.  Tracks a mount-point set in memory, records
  every mount/unmount call, and accepts predetermined per-call failures via
  `fail_for`.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MountResult:
    """Outcome of a single mount or unmount call."""

    ok: bool
    error: Optional[str] = None


class MountExecutor(Protocol):
    """The contract every executor must satisfy.

    Implementations should never raise for I/O failures; instead, return a
    MountResult(ok=False, error="…").  Raising is reserved for programmer
    errors (bad arguments, etc.).
    """

    def mount(
        self,
        device: str,
        mount_point: str,
        fstype: str,
        options: str,
    ) -> MountResult: ...

    def unmount(self, mount_point: str) -> MountResult: ...

    def current_mount_points(self, prefix: str = "/media") -> set[str]: ...


# --- Production implementation -------------------------------------------

MOUNT_TIMEOUT_SECONDS = 30


class SubprocessMountExecutor:
    """Executes mount/umount via subprocess and parses /proc/mounts."""

    def __init__(self, timeout_seconds: int = MOUNT_TIMEOUT_SECONDS):
        self._timeout = timeout_seconds

    def mount(
        self,
        device: str,
        mount_point: str,
        fstype: str,
        options: str,
    ) -> MountResult:
        cmd = ["mount", "-t", fstype, "-o", options, device, mount_point]
        return self._run(cmd, label=f"mount {device} {mount_point}")

    def unmount(self, mount_point: str) -> MountResult:
        # Plain umount.  If the mount is busy, the reconciler will see it
        # still present on the next pass and retry; we deliberately do not
        # add `-l` (lazy) here because lazy unmounts can hide bugs.
        return self._run(["umount", mount_point], label=f"umount {mount_point}")

    def current_mount_points(self, prefix: str = "/media") -> set[str]:
        out: set[str] = set()
        try:
            with open("/proc/mounts") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].startswith(prefix):
                        out.add(parts[1])
        except OSError as e:
            logger.error("Could not read /proc/mounts: %s", e)
        return out

    def _run(self, cmd: list[str], *, label: str) -> MountResult:
        logger.info("Running: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            return MountResult(
                ok=False,
                error=f"{label}: timed out after {self._timeout}s",
            )
        if result.returncode != 0:
            return MountResult(
                ok=False,
                error=f"{label}: {result.stderr.strip() or 'non-zero exit'}",
            )
        return MountResult(ok=True)


# --- Test fake ------------------------------------------------------------

@dataclass
class MountCall:
    """Recorded mount invocation, for test assertions."""

    device: str
    mount_point: str
    fstype: str
    options: str


@dataclass
class UnmountCall:
    """Recorded unmount invocation, for test assertions."""

    mount_point: str


@dataclass
class FakeMountExecutor:
    """In-memory MountExecutor for tests.

    Behaviour:
      - mount(...) adds mount_point to the live set and records the call,
        unless the call matches an entry in ``fail_for_mount`` (matched by
        mount_point), in which case it returns a failure and the set is
        unchanged.
      - unmount(...) removes mount_point from the live set and records the
        call, unless the call matches ``fail_for_unmount``.
      - current_mount_points(prefix) returns a copy of the live set filtered
        by prefix.

    Tests can seed the live set via the ``initially_mounted`` argument.
    """

    initially_mounted: frozenset[str] = frozenset()
    fail_for_mount: frozenset[str] = frozenset()
    fail_for_unmount: frozenset[str] = frozenset()
    mount_calls: list[MountCall] = field(default_factory=list)
    unmount_calls: list[UnmountCall] = field(default_factory=list)
    _live: set[str] = field(init=False)

    def __post_init__(self) -> None:
        self._live = set(self.initially_mounted)

    def mount(
        self,
        device: str,
        mount_point: str,
        fstype: str,
        options: str,
    ) -> MountResult:
        self.mount_calls.append(MountCall(device, mount_point, fstype, options))
        if mount_point in self.fail_for_mount:
            return MountResult(ok=False, error=f"fake: configured to fail mount {mount_point}")
        self._live.add(mount_point)
        return MountResult(ok=True)

    def unmount(self, mount_point: str) -> MountResult:
        self.unmount_calls.append(UnmountCall(mount_point))
        if mount_point in self.fail_for_unmount:
            return MountResult(ok=False, error=f"fake: configured to fail umount {mount_point}")
        self._live.discard(mount_point)
        return MountResult(ok=True)

    def current_mount_points(self, prefix: str = "/media") -> set[str]:
        return {mp for mp in self._live if mp.startswith(prefix)}
