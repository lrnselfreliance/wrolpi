"""
Unit tests for controller.lib.disks module.
"""

import json
from unittest import mock

import pytest

from controller.lib.disks import (
    BlockDevice,
    get_block_devices,
    get_uuid,
    get_wrolpi_uid_gid,
    validate_mount_point,
    mount_drive,
    unmount_drive,
    is_mount_busy,
    get_mounts,
)


class TestBlockDevice:
    """Tests for BlockDevice dataclass."""

    def test_create_block_device(self):
        """Should create a BlockDevice instance."""
        device = BlockDevice(
            name="sda1",
            path="/dev/sda1",
            size="100G",
            fstype="ext4",
            mountpoint="/media/data",
            label="DATA",
            uuid="1234-5678",
            model="Samsung SSD",
        )
        assert device.name == "sda1"
        assert device.path == "/dev/sda1"
        assert device.is_wrolpi_drive is False

    def test_block_device_defaults(self):
        """Should have default values."""
        device = BlockDevice(
            name="sda1",
            path="/dev/sda1",
            size="100G",
            fstype=None,
            mountpoint=None,
            label=None,
            uuid=None,
            model=None,
        )
        assert device.is_wrolpi_drive is False


class TestGetBlockDevices:
    """Tests for get_block_devices function."""

    def test_returns_empty_in_docker_mode(self):
        """Should return empty list in Docker mode."""
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=True):
            result = get_block_devices()
            assert result == []

    def test_returns_devices_from_lsblk(self):
        """Should parse lsblk output and return devices."""
        lsblk_output = json.dumps({
            "blockdevices": [
                {
                    "name": "sda",
                    "path": "/dev/sda",
                    "size": "500G",
                    "type": "disk",
                    "model": "Samsung SSD",
                    "children": [
                        {
                            "name": "sda1",
                            "path": "/dev/sda1",
                            "size": "500G",
                            "type": "part",
                            "fstype": "ext4",
                            "mountpoint": "/media/data",
                            "label": "DATA",
                            "uuid": "1234-5678",
                        }
                    ]
                }
            ]
        })
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout=lsblk_output)
                result = get_block_devices()
                assert len(result) == 1
                assert result[0].name == "sda1"
                assert result[0].fstype == "ext4"
                assert result[0].model == "Samsung SSD"

    def test_filters_unsupported_filesystems(self):
        """Should only return devices with supported filesystems."""
        lsblk_output = json.dumps({
            "blockdevices": [
                {
                    "name": "sda",
                    "type": "disk",
                    "children": [
                        {"name": "sda1", "path": "/dev/sda1", "size": "100G", "type": "part", "fstype": "ext4"},
                        {"name": "sda2", "path": "/dev/sda2", "size": "100G", "type": "part", "fstype": "ntfs"},
                    ]
                }
            ]
        })
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout=lsblk_output)
                result = get_block_devices()
                assert len(result) == 1
                assert result[0].name == "sda1"

    def test_handles_lsblk_failure(self):
        """Should return empty list on lsblk failure."""
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="error")
                result = get_block_devices()
                assert result == []


class TestGetUuid:
    """Tests for get_uuid function."""

    def test_returns_uuid_from_blkid(self):
        """Should return UUID from blkid output."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="1234-5678-90ab\n")
            result = get_uuid("/dev/sda1")
            assert result == "1234-5678-90ab"

    def test_returns_none_on_failure(self):
        """Should return None if blkid fails."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=1, stdout="")
            result = get_uuid("/dev/sda1")
            assert result is None


class TestValidateMountPoint:
    """Tests for validate_mount_point function."""

    def test_accepts_media_path(self):
        """Should accept paths under /media."""
        validate_mount_point("/media/wrolpi")
        validate_mount_point("/media/usb")
        validate_mount_point("/media/wrolpi/data")

    def test_rejects_non_media_paths(self):
        """Should reject paths not under /media."""
        with pytest.raises(ValueError, match="must be under /media"):
            validate_mount_point("/mnt/data")

        with pytest.raises(ValueError, match="must be under /media"):
            validate_mount_point("/home/user")

        with pytest.raises(ValueError, match="must be under /media"):
            validate_mount_point("/")

    def test_rejects_path_traversal(self):
        """Should reject path traversal attempts."""
        with pytest.raises(ValueError):
            validate_mount_point("/media/../etc")


class TestMountDrive:
    """Tests for mount_drive function."""

    def test_returns_error_in_docker_mode(self):
        """Should return error in Docker mode."""
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=True):
            result = mount_drive("/dev/sda1", "/media/test")
            assert result["success"] is False
            assert "Docker" in result["error"]

    def test_validates_mount_point(self):
        """Should validate mount point."""
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=False):
            result = mount_drive("/dev/sda1", "/mnt/test")
            assert result["success"] is False
            assert "must be under /media" in result["error"]

    def test_mounts_drive_successfully(self):
        """Should mount drive successfully."""
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=False):
            with mock.patch("pathlib.Path.mkdir"):
                with mock.patch("subprocess.run") as mock_run:
                    mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
                    result = mount_drive("/dev/sda1", "/media/test")
                    assert result["success"] is True
                    assert result["mount_point"] == "/media/test"

    def test_handles_mount_failure(self):
        """Should handle mount failure."""
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=False):
            with mock.patch("pathlib.Path.mkdir"):
                with mock.patch("subprocess.run") as mock_run:
                    mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="mount failed")
                    result = mount_drive("/dev/sda1", "/media/test")
                    assert result["success"] is False
                    assert "mount failed" in result["error"]

    def test_exfat_mount_includes_uid_gid(self):
        """Should add uid/gid options when mounting exfat."""
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.disks.get_wrolpi_uid_gid", return_value=(1001, 1001)):
                with mock.patch("pathlib.Path.mkdir"):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
                        result = mount_drive("/dev/sda1", "/media/test", fstype="exfat")
                        assert result["success"] is True
                        # Verify mount was called with uid/gid options
                        call_args = mock_run.call_args[0][0]
                        assert "-o" in call_args
                        options_idx = call_args.index("-o") + 1
                        options = call_args[options_idx]
                        assert "uid=1001" in options
                        assert "gid=1001" in options

    def test_ext4_mount_does_not_include_uid_gid(self):
        """Should not add uid/gid options when mounting ext4."""
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=False):
            with mock.patch("pathlib.Path.mkdir"):
                with mock.patch("subprocess.run") as mock_run:
                    mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
                    result = mount_drive("/dev/sda1", "/media/test", fstype="ext4")
                    assert result["success"] is True
                    # Verify mount was called without uid/gid options
                    call_args = mock_run.call_args[0][0]
                    assert "-o" in call_args
                    options_idx = call_args.index("-o") + 1
                    options = call_args[options_idx]
                    assert "uid=" not in options
                    assert "gid=" not in options

    def test_vfat_mount_includes_uid_gid(self):
        """Should add uid/gid options when mounting vfat (FAT32)."""
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.disks.get_wrolpi_uid_gid", return_value=(1001, 1001)):
                with mock.patch("pathlib.Path.mkdir"):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
                        result = mount_drive("/dev/sda1", "/media/test", fstype="vfat")
                        assert result["success"] is True
                        # Verify mount was called with uid/gid options
                        call_args = mock_run.call_args[0][0]
                        assert "-o" in call_args
                        options_idx = call_args.index("-o") + 1
                        options = call_args[options_idx]
                        assert "uid=1001" in options
                        assert "gid=1001" in options


class TestGetWrolpiUidGid:
    """Tests for get_wrolpi_uid_gid function."""

    def test_returns_wrolpi_user_ids(self):
        """Should return uid/gid for wrolpi user when it exists."""
        mock_pwd = mock.Mock()
        mock_pwd.pw_uid = 1001
        mock_grp = mock.Mock()
        mock_grp.gr_gid = 1001

        with mock.patch("controller.lib.disks.pwd.getpwnam", return_value=mock_pwd):
            with mock.patch("controller.lib.disks.grp.getgrnam", return_value=mock_grp):
                uid, gid = get_wrolpi_uid_gid()
                assert uid == 1001
                assert gid == 1001

    def test_returns_fallback_when_user_not_found(self):
        """Should return 1001:1001 fallback when wrolpi user doesn't exist."""
        with mock.patch("controller.lib.disks.pwd.getpwnam", side_effect=KeyError("wrolpi")):
            uid, gid = get_wrolpi_uid_gid()
            assert uid == 1001
            assert gid == 1001


class TestUnmountDrive:
    """Tests for unmount_drive function."""

    def test_returns_error_in_docker_mode(self):
        """Should return error in Docker mode."""
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=True):
            result = unmount_drive("/media/test")
            assert result["success"] is False
            assert "Docker" in result["error"]

    def test_protects_primary_wrolpi_mount(self):
        """Should protect /media/wrolpi from accidental unmount."""
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.disks.get_config", return_value={"drives": {}}):
                result = unmount_drive("/media/wrolpi")
                assert result["success"] is False
                assert "Cannot unmount /media/wrolpi" in result["error"]

    def test_unmounts_successfully(self):
        """Should unmount successfully."""
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.disks.is_mount_busy", return_value=False):
                with mock.patch("subprocess.run") as mock_run:
                    mock_run.return_value = mock.Mock(returncode=0)
                    result = unmount_drive("/media/test")
                    assert result["success"] is True

    def test_checks_if_mount_busy(self):
        """Should check if mount is busy."""
        with mock.patch("controller.lib.disks.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.disks.is_mount_busy", return_value=True):
                result = unmount_drive("/media/test", lazy=False)
                assert result["success"] is False
                assert "busy" in result["error"]


class TestIsMountBusy:
    """Tests for is_mount_busy function."""

    def test_returns_true_if_processes_using(self):
        """Should return True if processes are using mount."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="python /media/test/file.py")
            result = is_mount_busy("/media/test")
            # is_mount_busy returns truthy value (non-empty string) when busy
            assert result

    def test_returns_false_if_no_processes(self):
        """Should return False if no processes using mount."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=1, stdout="")
            result = is_mount_busy("/media/test")
            assert not result


class TestGetMounts:
    """Tests for get_mounts function."""

    def test_returns_mounts_under_media(self):
        """Should return mounts under /media."""
        findmnt_output = json.dumps({
            "filesystems": [
                {"target": "/", "source": "/dev/sda1", "fstype": "ext4", "options": "rw"},
                {"target": "/media/wrolpi", "source": "/dev/sdb1", "fstype": "ext4", "options": "rw"},
                {"target": "/media/usb", "source": "/dev/sdc1", "fstype": "vfat", "options": "rw"},
            ]
        })
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout=findmnt_output)
            result = get_mounts()
            assert len(result) == 2
            assert result[0]["mount_point"] == "/media/wrolpi"
            assert result[1]["mount_point"] == "/media/usb"


