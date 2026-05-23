"""
Tests for controller.lib.mount_executor.

The fake is a load-bearing test double; if it lies the entire Reconciler
test suite is meaningless.  These tests pin its behaviour without using
mocks.  The Subprocess executor is exercised against its own narrow
abstraction (a subprocess.run replacement injected via a small seam) so
the production path is also covered without leaning on real mount(8).
"""

from controller.lib.mount_executor import (
    FakeMountExecutor,
    MountCall,
    MountResult,
    SubprocessMountExecutor,
    UnmountCall,
)


# --- FakeMountExecutor --------------------------------------------------

class TestFakeMountExecutorState:

    def test_starts_with_initially_mounted(self):
        fake = FakeMountExecutor(initially_mounted=frozenset({"/media/a", "/media/b"}))
        assert fake.current_mount_points() == {"/media/a", "/media/b"}

    def test_mount_adds_to_live_set(self):
        fake = FakeMountExecutor()
        r = fake.mount("UUID=1", "/media/x", "ext4", "defaults")
        assert r.ok is True
        assert r.error is None
        assert fake.current_mount_points() == {"/media/x"}

    def test_unmount_removes_from_live_set(self):
        fake = FakeMountExecutor(initially_mounted=frozenset({"/media/x"}))
        r = fake.unmount("/media/x")
        assert r.ok is True
        assert fake.current_mount_points() == set()

    def test_unmount_of_missing_path_is_still_recorded(self):
        # We model umount(8): unmounting an unmounted path is allowed (it's
        # not an error in the fake).  The Reconciler is responsible for
        # only calling unmount on currently-mounted paths.
        fake = FakeMountExecutor()
        r = fake.unmount("/media/never-mounted")
        assert r.ok is True
        assert fake.unmount_calls == [UnmountCall("/media/never-mounted")]

    def test_prefix_filter(self):
        fake = FakeMountExecutor(initially_mounted=frozenset(
            {"/media/a", "/media/b", "/mnt/c"}))
        # The fake stores anything but current_mount_points filters.
        assert fake.current_mount_points("/media") == {"/media/a", "/media/b"}
        assert fake.current_mount_points("/mnt") == {"/mnt/c"}


class TestFakeMountExecutorCallRecording:

    def test_records_mount_arguments(self):
        fake = FakeMountExecutor()
        fake.mount("UUID=1234", "/media/x", "ext4", "defaults,nofail")
        assert fake.mount_calls == [
            MountCall("UUID=1234", "/media/x", "ext4", "defaults,nofail"),
        ]

    def test_records_unmount_arguments(self):
        fake = FakeMountExecutor(initially_mounted=frozenset({"/media/x"}))
        fake.unmount("/media/x")
        assert fake.unmount_calls == [UnmountCall("/media/x")]


class TestFakeMountExecutorConfiguredFailures:

    def test_mount_failure_leaves_set_unchanged(self):
        fake = FakeMountExecutor(fail_for_mount=frozenset({"/media/bad"}))
        r = fake.mount("UUID=1", "/media/bad", "ext4", "defaults")
        assert r.ok is False
        assert "fake" in (r.error or "")
        assert fake.current_mount_points() == set()
        # Call still recorded so tests can assert what was attempted.
        assert len(fake.mount_calls) == 1

    def test_unmount_failure_leaves_set_unchanged(self):
        fake = FakeMountExecutor(
            initially_mounted=frozenset({"/media/x"}),
            fail_for_unmount=frozenset({"/media/x"}),
        )
        r = fake.unmount("/media/x")
        assert r.ok is False
        assert "/media/x" in fake.current_mount_points()


# --- SubprocessMountExecutor --------------------------------------------

class _FakeCompletedProcess:
    def __init__(self, returncode: int, stderr: str = ""):
        self.returncode = returncode
        self.stderr = stderr


class TestSubprocessMountExecutor:
    """Cover the subprocess-backed executor without ever invoking mount(8).

    We inject a fake subprocess.run into the executor's module namespace via
    monkeypatch (pytest's built-in feature, not mock.patch).  This is the
    closest the suite gets to mocking — it's necessary because subprocess is
    the boundary that real I/O lives on.
    """

    def test_mount_success(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeCompletedProcess(returncode=0)

        monkeypatch.setattr(
            "controller.lib.mount_executor.subprocess.run", fake_run,
        )
        executor = SubprocessMountExecutor()
        result = executor.mount("UUID=1", "/media/x", "ext4", "defaults")
        assert result == MountResult(ok=True)
        assert calls == [["mount", "-t", "ext4", "-o", "defaults",
                          "UUID=1", "/media/x"]]

    def test_mount_propagates_stderr(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            return _FakeCompletedProcess(returncode=32, stderr="busy")

        monkeypatch.setattr(
            "controller.lib.mount_executor.subprocess.run", fake_run,
        )
        result = SubprocessMountExecutor().mount(
            "UUID=1", "/media/x", "ext4", "defaults")
        assert result.ok is False
        assert "busy" in (result.error or "")

    def test_mount_timeout(self, monkeypatch):
        import subprocess as _sp

        def fake_run(cmd, **kwargs):
            raise _sp.TimeoutExpired(cmd=cmd, timeout=30)

        monkeypatch.setattr(
            "controller.lib.mount_executor.subprocess.run", fake_run,
        )
        result = SubprocessMountExecutor().mount(
            "UUID=1", "/media/x", "ext4", "defaults")
        assert result.ok is False
        assert "timed out" in (result.error or "")

    def test_unmount_command_shape(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeCompletedProcess(returncode=0)

        monkeypatch.setattr(
            "controller.lib.mount_executor.subprocess.run", fake_run,
        )
        SubprocessMountExecutor().unmount("/media/x")
        assert calls == [["umount", "/media/x"]]

    def test_current_mount_points_parses_proc_mounts(self, monkeypatch, tmp_path):
        # Redirect /proc/mounts to a temp file the executor will read.
        proc_mounts = tmp_path / "proc-mounts"
        proc_mounts.write_text(
            "proc /proc proc rw 0 0\n"
            "/dev/sda1 / ext4 rw 0 0\n"
            "/dev/sdb1 /media/wrolpi/usb ext4 rw 0 0\n"
            "tmpfs /tmp tmpfs rw 0 0\n"
            "/dev/sdc1 /media/photos exfat rw 0 0\n"
        )

        # Patch only the open(...) lookup the executor performs.  We do this
        # via monkeypatch on builtins.open scoped to this test only.
        original_open = open

        def open_redirect(path, *args, **kwargs):
            if path == "/proc/mounts":
                return original_open(proc_mounts, *args, **kwargs)
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", open_redirect)

        executor = SubprocessMountExecutor()
        assert executor.current_mount_points("/media") == {
            "/media/wrolpi/usb", "/media/photos",
        }
