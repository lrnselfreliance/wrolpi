"""
Tests for controller.lib.reconciler.

The reconciler is pure orchestration: it reads fstab.yaml, asks an injected
MountExecutor what is live, then issues mount/unmount calls.  These tests
use FakeMountExecutor + real fstab.yaml files in tmp_path.  No mocks, no
patches.

Every test reads top-to-bottom:
    1. set up fstab.yaml on disk
    2. construct a FakeMountExecutor with the live state at the start of
       the test
    3. run reconciler.apply()
    4. assert on the result and on the executor's recorded calls
"""

from pathlib import Path

from controller.lib.fstab_yaml import FstabEntry, FstabFile, save as save_fstab
from controller.lib.mount_executor import FakeMountExecutor, MountCall, UnmountCall
from controller.lib.reconciler import (
    RESERVED_MOUNT_POINTS,
    ReconcileResult,
    Reconciler,
)


# --- Helpers --------------------------------------------------------------

def make_reconciler(
    tmp_path: Path,
    *,
    fstab: FstabFile = None,
    executor: FakeMountExecutor = None,
    managed: set[str] = None,
    wrolpi_uid: int = 1001,
    wrolpi_gid: int = 1001,
) -> tuple[Reconciler, FakeMountExecutor]:
    fstab_path = tmp_path / "fstab.yaml"
    managed_path = tmp_path / "managed"
    save_fstab(fstab if fstab is not None else FstabFile(), fstab_path)
    if managed:
        managed_path.write_text("\n".join(sorted(managed)) + "\n")
    fake = executor if executor is not None else FakeMountExecutor()
    rec = Reconciler(
        executor=fake,
        fstab_path=fstab_path,
        managed_path=managed_path,
        wrolpi_uid=wrolpi_uid,
        wrolpi_gid=wrolpi_gid,
    )
    return rec, fake


def _entry(device="UUID=1", mount_point="/media/wrolpi/usb",
           fstype="ext4", options="defaults"):
    return FstabEntry(device, mount_point, fstype, options)


# --- Mount path -----------------------------------------------------------

class TestMounts:

    def test_empty_fstab_is_noop(self, tmp_path):
        rec, fake = make_reconciler(tmp_path)
        result = rec.apply()
        assert result == ReconcileResult()
        assert fake.mount_calls == []
        assert fake.unmount_calls == []

    def test_mounts_a_missing_entry(self, tmp_path):
        rec, fake = make_reconciler(tmp_path, fstab=FstabFile(mounts=[_entry()]))
        result = rec.apply()
        assert result.mounted == ["/media/wrolpi/usb"]
        assert fake.mount_calls == [MountCall(
            "UUID=1", "/media/wrolpi/usb", "ext4", "defaults",
        )]
        assert fake.unmount_calls == []

    def test_skips_already_mounted(self, tmp_path):
        fake = FakeMountExecutor(initially_mounted=frozenset({"/media/wrolpi/usb"}))
        rec, fake = make_reconciler(
            tmp_path, fstab=FstabFile(mounts=[_entry()]), executor=fake)
        result = rec.apply()
        assert result.mounted == []
        assert fake.mount_calls == []
        # Diagnostics explain the "nothing to do" run in the journal.
        assert result.desired_count == 1
        assert result.already_mounted == ["/media/wrolpi/usb"]

    def test_empty_fstab_reports_zero_desired(self, tmp_path):
        rec, fake = make_reconciler(tmp_path, fstab=FstabFile())
        result = rec.apply()
        assert result.desired_count == 0
        assert result.already_mounted == []

    def test_mount_failure_is_recorded(self, tmp_path):
        fake = FakeMountExecutor(fail_for_mount=frozenset({"/media/wrolpi/usb"}))
        rec, fake = make_reconciler(
            tmp_path, fstab=FstabFile(mounts=[_entry()]), executor=fake)
        result = rec.apply()
        assert result.mounted == []
        assert len(result.mount_failures) == 1
        assert result.mount_failures[0][0] == "/media/wrolpi/usb"
        assert result.all_succeeded is False

    def test_continues_after_individual_failure(self, tmp_path):
        # First entry fails; second still gets mounted — never block the
        # boot because of one bad drive.
        fake = FakeMountExecutor(fail_for_mount=frozenset({"/media/wrolpi/usb"}))
        fstab = FstabFile(mounts=[
            _entry(device="UUID=1", mount_point="/media/wrolpi/usb"),
            _entry(device="UUID=2", mount_point="/media/wrolpi/2tb"),
        ])
        rec, fake = make_reconciler(tmp_path, fstab=fstab, executor=fake)
        result = rec.apply()
        assert result.mounted == ["/media/wrolpi/2tb"]
        assert len(result.mount_failures) == 1


# --- Unmount path ---------------------------------------------------------

class TestUnmounts:

    def test_unmounts_removed_managed_path(self, tmp_path):
        # Previously mounted by us, still live, but no longer in fstab.yaml
        # — must be unmounted.
        fake = FakeMountExecutor(initially_mounted=frozenset({"/media/wrolpi/usb"}))
        rec, fake = make_reconciler(
            tmp_path,
            fstab=FstabFile(),
            managed={"/media/wrolpi/usb"},
            executor=fake,
        )
        result = rec.apply()
        assert result.unmounted == ["/media/wrolpi/usb"]
        assert fake.unmount_calls == [UnmountCall("/media/wrolpi/usb")]

    def test_does_not_unmount_unmanaged_path(self, tmp_path):
        # User has /media/photos mounted manually — fstab.yaml is empty and
        # managed set is empty.  Reconciler must NOT touch /media/photos.
        fake = FakeMountExecutor(initially_mounted=frozenset({"/media/photos"}))
        rec, fake = make_reconciler(tmp_path, fstab=FstabFile(), executor=fake)
        result = rec.apply()
        assert result.unmounted == []
        assert fake.unmount_calls == []

    def test_does_not_unmount_when_still_in_fstab(self, tmp_path):
        # In managed AND in fstab.yaml AND live — leave alone.
        fake = FakeMountExecutor(initially_mounted=frozenset({"/media/wrolpi/usb"}))
        rec, fake = make_reconciler(
            tmp_path,
            fstab=FstabFile(mounts=[_entry()]),
            managed={"/media/wrolpi/usb"},
            executor=fake,
        )
        result = rec.apply()
        assert result.unmounted == []
        assert fake.unmount_calls == []

    def test_unmount_failure_keeps_path_in_managed_set(self, tmp_path):
        fake = FakeMountExecutor(
            initially_mounted=frozenset({"/media/wrolpi/usb"}),
            fail_for_unmount=frozenset({"/media/wrolpi/usb"}),
        )
        rec, fake = make_reconciler(
            tmp_path,
            fstab=FstabFile(),
            managed={"/media/wrolpi/usb"},
            executor=fake,
        )
        result = rec.apply()
        assert result.unmounted == []
        assert len(result.unmount_failures) == 1
        # Path still appears managed so a future retry can unmount it.
        managed_after = (tmp_path / "managed").read_text().splitlines()
        assert "/media/wrolpi/usb" in managed_after

    def test_stale_managed_path_not_live_is_dropped(self, tmp_path):
        # Reconciler restarts after a reboot; managed file says we owned
        # /media/wrolpi/usb but it's not currently mounted (live-boot
        # didn't restore it).  Just forget it; don't try to unmount.
        fake = FakeMountExecutor()
        rec, fake = make_reconciler(
            tmp_path,
            fstab=FstabFile(),
            managed={"/media/wrolpi/usb"},
            executor=fake,
        )
        result = rec.apply()
        assert result.unmounted == []
        assert fake.unmount_calls == []
        managed_after = (tmp_path / "managed").read_text()
        assert "/media/wrolpi/usb" not in managed_after


# --- Reserved + outside-/media protection --------------------------------

class TestSkips:

    def test_reserved_mount_point_is_skipped(self, tmp_path):
        # /media/wrolpi appearing in fstab.yaml (e.g. via migration of the
        # primary line) must be ignored, not re-mounted.
        for mp in RESERVED_MOUNT_POINTS:
            fstab = FstabFile(mounts=[_entry(mount_point=mp)])
            rec, fake = make_reconciler(tmp_path, fstab=fstab)
            result = rec.apply()
            assert fake.mount_calls == [], mp
            assert (mp, "reserved mount point") in result.skipped, mp

    def test_outside_media_is_skipped(self, tmp_path):
        fstab = FstabFile(mounts=[_entry(mount_point="/mnt/elsewhere")])
        rec, fake = make_reconciler(tmp_path, fstab=fstab)
        result = rec.apply()
        assert fake.mount_calls == []
        assert any(
            mp == "/mnt/elsewhere" and "outside /media" in reason
            for mp, reason in result.skipped
        )

    def test_missing_device_or_mount_point_is_skipped(self, tmp_path):
        fstab = FstabFile(mounts=[
            FstabEntry(device="", mount_point="/media/wrolpi/x", fstype="ext4"),
            FstabEntry(device="UUID=1", mount_point="", fstype="ext4"),
        ])
        rec, fake = make_reconciler(tmp_path, fstab=fstab)
        result = rec.apply()
        assert fake.mount_calls == []
        assert len(result.skipped) == 2


# --- exfat/vfat option injection -----------------------------------------

class TestUidGidInjection:

    def test_injects_uid_gid_for_exfat(self, tmp_path):
        fstab = FstabFile(mounts=[_entry(fstype="exfat")])
        rec, fake = make_reconciler(tmp_path, fstab=fstab,
                                    wrolpi_uid=2000, wrolpi_gid=2000)
        rec.apply()
        opts = fake.mount_calls[0].options
        assert "uid=2000" in opts
        assert "gid=2000" in opts

    def test_does_not_double_inject_if_user_already_supplied(self, tmp_path):
        fstab = FstabFile(mounts=[_entry(fstype="vfat",
                                         options="defaults,uid=1234,gid=1234")])
        rec, fake = make_reconciler(tmp_path, fstab=fstab,
                                    wrolpi_uid=2000, wrolpi_gid=2000)
        rec.apply()
        opts = fake.mount_calls[0].options
        assert opts.count("uid=") == 1
        assert "uid=1234" in opts

    def test_ext4_options_untouched(self, tmp_path):
        fstab = FstabFile(mounts=[_entry(fstype="ext4", options="defaults,noatime")])
        rec, fake = make_reconciler(tmp_path, fstab=fstab,
                                    wrolpi_uid=2000, wrolpi_gid=2000)
        rec.apply()
        opts = fake.mount_calls[0].options
        assert opts == "defaults,noatime"

    def test_no_uid_gid_when_unknown(self, tmp_path):
        fstab = FstabFile(mounts=[_entry(fstype="exfat")])
        rec, fake = make_reconciler(tmp_path, fstab=fstab,
                                    wrolpi_uid=None, wrolpi_gid=None)
        rec.apply()
        opts = fake.mount_calls[0].options
        assert "uid=" not in opts


# --- Managed-set persistence ---------------------------------------------

class TestManagedSetPersistence:

    def test_first_mount_writes_managed_entry(self, tmp_path):
        rec, fake = make_reconciler(tmp_path, fstab=FstabFile(mounts=[_entry()]))
        rec.apply()
        managed_after = (tmp_path / "managed").read_text().splitlines()
        assert "/media/wrolpi/usb" in managed_after

    def test_successful_unmount_removes_from_managed(self, tmp_path):
        fake = FakeMountExecutor(initially_mounted=frozenset({"/media/wrolpi/usb"}))
        rec, fake = make_reconciler(
            tmp_path,
            fstab=FstabFile(),
            managed={"/media/wrolpi/usb"},
            executor=fake,
        )
        rec.apply()
        managed_after = (tmp_path / "managed").read_text()
        assert "/media/wrolpi/usb" not in managed_after

    def test_idempotent_runs_keep_managed_stable(self, tmp_path):
        fstab = FstabFile(mounts=[_entry()])
        rec, fake = make_reconciler(tmp_path, fstab=fstab)
        rec.apply()
        first = (tmp_path / "managed").read_text()
        rec.apply()
        second = (tmp_path / "managed").read_text()
        assert first == second
        # Mount called exactly once (second run sees it live and skips).
        assert len(fake.mount_calls) == 1
