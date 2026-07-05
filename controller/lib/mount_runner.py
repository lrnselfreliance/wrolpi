"""
Entry point for wrolpi-mounts.service.

This module is intentionally tiny: it wires up production dependencies
(real subprocess executor, real wrolpi uid/gid lookup, real fstab.yaml on
the drive) and asks the Reconciler to apply.  All real work lives in
controller.lib.reconciler; tests for the orchestration live in
test_reconciler.py using FakeMountExecutor.
"""

from __future__ import annotations

import logging
import sys

from controller.lib.disks import get_wrolpi_uid_gid
from controller.lib.fstab_migration import migrate_etc_fstab
from controller.lib.mount_executor import SubprocessMountExecutor
from controller.lib.reconciler import DEFAULT_FSTAB_PATH, Reconciler

logger = logging.getLogger(__name__)


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s wrolpi-mounts: %(message)s",
    )

    # Migration is idempotent (marker-gated).  Doing it here means a freshly
    # upgraded WROLPi picks up legacy /etc/fstab entries on the first boot
    # of the new mount system, before we try to apply them.
    try:
        migrate_etc_fstab()
    except Exception as e:  # noqa: BLE001 - never fail boot on migration error
        logger.error("fstab migration raised, continuing without it: %s", e)

    try:
        wrolpi_uid, wrolpi_gid = get_wrolpi_uid_gid()
    except Exception as e:  # noqa: BLE001 - best-effort enrichment
        logger.warning("Could not resolve wrolpi uid/gid (%s)", e)
        wrolpi_uid, wrolpi_gid = None, None

    reconciler = Reconciler(
        executor=SubprocessMountExecutor(),
        wrolpi_uid=wrolpi_uid,
        wrolpi_gid=wrolpi_gid,
    )
    result = reconciler.apply()

    if result.desired_count == 0:
        logger.info("%s lists no mounts; nothing to reconcile.", DEFAULT_FSTAB_PATH)
    logger.info(
        "Reconcile complete: %d desired, %d already mounted, %d skipped, "
        "%d mounted, %d unmounted, %d mount failures, %d unmount failures",
        result.desired_count, len(result.already_mounted), len(result.skipped),
        len(result.mounted), len(result.unmounted),
        len(result.mount_failures), len(result.unmount_failures),
    )
    for mp in result.already_mounted:
        logger.info("Already mounted: %s", mp)
    for mp, reason in result.skipped:
        logger.info("Skipped %s: %s", mp, reason)
    for mp, err in result.mount_failures:
        logger.error("Failed to mount %s: %s", mp, err)
    for mp, err in result.unmount_failures:
        logger.error("Failed to unmount %s: %s", mp, err)

    # Always return 0: the service must not block boot if a single mount
    # is broken.  Failures are logged and surfaced via the journal.
    return 0


if __name__ == "__main__":
    sys.exit(main())
