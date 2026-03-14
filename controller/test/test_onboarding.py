"""
Unit tests for onboarding orchestration logic.
"""

from pathlib import Path
from unittest import mock

import pytest
import yaml

from controller.lib.onboarding import (
    TEMP_MOUNT_PATH,
    cancel_probe,
    commit_onboarding,
    get_onboarding_candidates,
    probe_drive,
)


class TestGetOnboardingCandidates:
    """Tests for get_onboarding_candidates."""

    def test_excludes_wrolpi_primary_mount(self, mock_docker_mode):
        """Drives mounted at /media/wrolpi should not appear as candidates."""
        from controller.lib.disks import BlockDevice

        devices = [
            BlockDevice(
                name="sda1", path="/dev/sda1", size="500G", fstype="ext4",
                mountpoint="/media/wrolpi", label="wrolpi", uuid="abc", model="SanDisk",
            ),
            BlockDevice(
                name="sdb1", path="/dev/sdb1", size="1T", fstype="ext4",
                mountpoint=None, label="backup", uuid="def", model="WD",
            ),
        ]
        with mock.patch("controller.lib.onboarding.get_block_devices", return_value=devices):
            candidates = get_onboarding_candidates()

        assert len(candidates) == 1
        assert candidates[0]["path"] == "/dev/sdb1"

    def test_excludes_system_mounts(self, mock_docker_mode):
        """Drives at /, /boot, /boot/firmware should be excluded."""
        from controller.lib.disks import BlockDevice

        devices = [
            BlockDevice(
                name="mmcblk0p1", path="/dev/mmcblk0p1", size="256M", fstype="vfat",
                mountpoint="/boot/firmware", label="boot", uuid="aaa", model=None,
            ),
            BlockDevice(
                name="mmcblk0p2", path="/dev/mmcblk0p2", size="32G", fstype="ext4",
                mountpoint="/", label="rootfs", uuid="bbb", model=None,
            ),
            BlockDevice(
                name="sda1", path="/dev/sda1", size="1T", fstype="ext4",
                mountpoint=None, label="data", uuid="ccc", model="WD",
            ),
        ]
        with mock.patch("controller.lib.onboarding.get_block_devices", return_value=devices):
            candidates = get_onboarding_candidates()

        assert len(candidates) == 1
        assert candidates[0]["path"] == "/dev/sda1"

    def test_includes_auto_mounted_drives(self, mock_docker_mode):
        """Drives auto-mounted under /media/pi/ should appear as candidates."""
        from controller.lib.disks import BlockDevice

        devices = [
            BlockDevice(
                name="sda1", path="/dev/sda1", size="500G", fstype="ext4",
                mountpoint="/media/pi/MyDrive", label="MyDrive", uuid="abc", model="SanDisk",
            ),
            BlockDevice(
                name="sdb1", path="/dev/sdb1", size="1T", fstype="ext4",
                mountpoint="/media/pi/Backup", label="Backup", uuid="def", model="WD",
            ),
        ]
        with mock.patch("controller.lib.onboarding.get_block_devices", return_value=devices):
            candidates = get_onboarding_candidates()

        assert len(candidates) == 2
        assert candidates[0]["mountpoint"] == "/media/pi/MyDrive"
        assert candidates[1]["mountpoint"] == "/media/pi/Backup"

    def test_returns_empty_in_docker(self, mock_docker_mode_enabled):
        """Docker mode returns no block devices, so no candidates."""
        candidates = get_onboarding_candidates()
        assert candidates == []

    def test_returns_all_unmounted(self, mock_docker_mode):
        """All unmounted drives should be candidates with mountpoint=None."""
        from controller.lib.disks import BlockDevice

        devices = [
            BlockDevice(
                name="sda1", path="/dev/sda1", size="500G", fstype="ext4",
                mountpoint=None, label=None, uuid="abc", model="SanDisk",
            ),
            BlockDevice(
                name="sdb1", path="/dev/sdb1", size="1T", fstype="btrfs",
                mountpoint=None, label="data", uuid="def", model=None,
            ),
        ]
        with mock.patch("controller.lib.onboarding.get_block_devices", return_value=devices):
            candidates = get_onboarding_candidates()

        assert len(candidates) == 2
        assert candidates[0]["fstype"] == "ext4"
        assert candidates[0]["mountpoint"] is None
        assert candidates[1]["fstype"] == "btrfs"

    def test_excludes_efi_partitions(self, mock_docker_mode):
        """EFI system partitions should not appear as candidates."""
        from controller.lib.disks import BlockDevice

        devices = [
            BlockDevice(
                name="sda1", path="/dev/sda1", size="200M", fstype="vfat",
                mountpoint=None, label="EFI", uuid="67E3-17ED", model="SanDisk",
            ),
            BlockDevice(
                name="sda2", path="/dev/sda2", size="500G", fstype="ext4",
                mountpoint=None, label="data", uuid="abc-123", model="SanDisk",
            ),
        ]
        with mock.patch("controller.lib.onboarding.get_block_devices", return_value=devices):
            candidates = get_onboarding_candidates()

        assert len(candidates) == 1
        assert candidates[0]["path"] == "/dev/sda2"

    def test_excludes_efi_partitions_case_insensitive(self, mock_docker_mode):
        """EFI label filtering should be case-insensitive."""
        from controller.lib.disks import BlockDevice

        devices = [
            BlockDevice(
                name="sda1", path="/dev/sda1", size="200M", fstype="vfat",
                mountpoint=None, label="efi", uuid="67E3-17ED", model="SanDisk",
            ),
        ]
        with mock.patch("controller.lib.onboarding.get_block_devices", return_value=devices):
            candidates = get_onboarding_candidates()

        assert len(candidates) == 0

    def test_excludes_temp_onboarding_mount(self, mock_docker_mode):
        """Drives mounted at the temp onboarding path should be excluded."""
        from controller.lib.disks import BlockDevice

        devices = [
            BlockDevice(
                name="sda1", path="/dev/sda1", size="500G", fstype="ext4",
                mountpoint="/media/wrolpi_temp_onboarding", label=None, uuid="abc", model="SanDisk",
            ),
        ]
        with mock.patch("controller.lib.onboarding.get_block_devices", return_value=devices):
            candidates = get_onboarding_candidates()

        assert len(candidates) == 0


class TestProbeDrive:
    """Tests for probe_drive."""

    def test_probe_with_config_present(self, mock_docker_mode, tmp_path):
        """Should find config and return mounts."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_data = {"drives": {"mounts": [
            {"device": "/dev/sda1", "mount_point": "/media/wrolpi", "fstype": "ext4"},
            {"device": "/dev/sdb1", "mount_point": "/media/backup", "fstype": "ext4"},
        ]}}
        (config_dir / "controller.yaml").write_text(yaml.dump(config_data))

        with mock.patch("controller.lib.onboarding.mount_drive", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.TEMP_MOUNT_PATH", str(tmp_path)), \
             mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch("controller.lib.onboarding._get_current_mountpoint", return_value=None):
            result = probe_drive("/dev/sda1", "ext4")

        assert result["success"] is True
        assert result["config_found"] is True
        assert len(result["mounts"]) == 2
        assert result["device_path"] == "/dev/sda1"

    def test_probe_detects_legacy_wrolpi_config(self, mock_docker_mode, tmp_path):
        """Should detect a WROLPi drive that has wrolpi.yaml but no controller.yaml."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "wrolpi.yaml").write_text("ignore_outdated_zims: true\n")

        with mock.patch("controller.lib.onboarding.mount_drive", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.TEMP_MOUNT_PATH", str(tmp_path)), \
             mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch("controller.lib.onboarding._get_current_mountpoint", return_value=None):
            result = probe_drive("/dev/sda1", "ext4")

        assert result["success"] is True
        assert result["config_found"] is True
        assert result["mounts"] == []

    def test_probe_with_no_config(self, mock_docker_mode, tmp_path):
        """Should report config_found=False when no config exists."""
        with mock.patch("controller.lib.onboarding.mount_drive", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.TEMP_MOUNT_PATH", str(tmp_path)), \
             mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch("controller.lib.onboarding._get_current_mountpoint", return_value=None):
            result = probe_drive("/dev/sda1", "ext4")

        assert result["success"] is True
        assert result["config_found"] is False
        assert result["mounts"] == []

    def test_probe_mount_failure(self, mock_docker_mode):
        """Should return error when mount fails."""
        with mock.patch(
            "controller.lib.onboarding.mount_drive",
            return_value={"success": False, "error": "Permission denied"},
        ), mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch("controller.lib.onboarding._get_current_mountpoint", return_value=None):
            result = probe_drive("/dev/sda1", "ext4")

        assert result["success"] is False
        assert "Permission denied" in result["error"]

    def test_probe_unmounts_auto_mounted_drive(self, mock_docker_mode, tmp_path):
        """Probe should unmount an auto-mounted drive before temp-mounting."""
        with mock.patch("controller.lib.onboarding.mount_drive", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.TEMP_MOUNT_PATH", str(tmp_path)), \
             mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch("controller.lib.onboarding._get_current_mountpoint", return_value="/media/pi/MyDrive"), \
             mock.patch("controller.lib.onboarding.unmount_drive", return_value={"success": True}) as mock_unmount:
            result = probe_drive("/dev/sda1", "ext4")

        assert result["success"] is True
        mock_unmount.assert_called_once_with("/media/pi/MyDrive", lazy=True)

    def test_probe_fails_if_unmount_fails(self, mock_docker_mode):
        """Probe should fail if the auto-mounted drive can't be unmounted."""
        with mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch("controller.lib.onboarding._get_current_mountpoint", return_value="/media/pi/MyDrive"), \
             mock.patch("controller.lib.onboarding.unmount_drive", return_value={"success": False, "error": "busy"}):
            result = probe_drive("/dev/sda1", "ext4")

        assert result["success"] is False
        assert "Failed to unmount" in result["error"]


class TestCommitOnboarding:
    """Tests for commit_onboarding."""

    def test_full_flow_with_config(self, mock_docker_mode, tmp_path):
        """Full onboarding with config file on drive."""
        media_dir = tmp_path / "wrolpi"
        media_dir.mkdir()
        config_dir = media_dir / "config"
        config_dir.mkdir()

        config_data = {"drives": {"mounts": [
            {"device": "/dev/sdb1", "mount_point": "/media/backup", "fstype": "ext4"},
        ]}}
        (config_dir / "controller.yaml").write_text(yaml.dump(config_data))

        with mock.patch("controller.lib.onboarding.get_media_directory", return_value=media_dir), \
             mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch("controller.lib.onboarding.mount_drive", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.add_fstab_entry", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.reload_config_from_drive", return_value=True), \
             mock.patch("controller.lib.onboarding.save_config"), \
             mock.patch("controller.lib.onboarding.start_script", return_value={"success": True}):
            result = commit_onboarding("/dev/sda1", "ext4")

        assert result["success"] is True
        assert str(media_dir) in result["mounts"]
        assert result["repair_started"] is True

    def test_fresh_drive_with_force(self, mock_docker_mode, tmp_path):
        """Fresh drive with force=True should succeed."""
        media_dir = tmp_path / "wrolpi"

        with mock.patch("controller.lib.onboarding.get_media_directory", return_value=media_dir), \
             mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch("controller.lib.onboarding.mount_drive", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.add_fstab_entry", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.reload_config_from_drive", return_value=False), \
             mock.patch("controller.lib.onboarding.save_config"), \
             mock.patch("controller.lib.onboarding.start_script", return_value={"success": True}):
            result = commit_onboarding("/dev/sda1", "ext4", force=True)

        assert result["success"] is True
        assert result["repair_started"] is True

    def test_cleans_transient_config_before_mount(self, mock_docker_mode, tmp_path):
        """Should delete transient SSL files before mounting the real drive."""
        media_dir = tmp_path / "wrolpi"
        media_dir.mkdir()
        # Simulate transient config created by generate_certificates.sh
        transient_config = media_dir / "config"
        transient_config.mkdir()
        transient_ssl = transient_config / "ssl"
        transient_ssl.mkdir()
        (transient_ssl / "ca.key").write_text("fake-key")
        (transient_ssl / "ca.crt").write_text("fake-cert")

        with mock.patch("controller.lib.onboarding.get_media_directory", return_value=media_dir), \
             mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch("controller.lib.onboarding.mount_drive", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.add_fstab_entry", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.reload_config_from_drive", return_value=False), \
             mock.patch("controller.lib.onboarding.save_config"), \
             mock.patch("controller.lib.onboarding.start_script", return_value={"success": True}):
            # media_dir is not a mount point (it's a tmp_path), so transient cleanup runs
            result = commit_onboarding("/dev/sda1", "ext4")

        assert result["success"] is True
        # Transient SSL files should have been removed before mount
        # (config dir is recreated by step 3, but the stale SSL should be gone)
        assert not transient_ssl.exists()
        assert not (transient_ssl / "ca.key").exists()

    def test_calls_save_config_after_reload(self, mock_docker_mode, tmp_path):
        """Should call save_config after reload to ensure controller.yaml exists."""
        media_dir = tmp_path / "wrolpi"

        with mock.patch("controller.lib.onboarding.get_media_directory", return_value=media_dir), \
             mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch("controller.lib.onboarding.mount_drive", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.add_fstab_entry", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.reload_config_from_drive", return_value=False), \
             mock.patch("controller.lib.onboarding.save_config") as mock_save, \
             mock.patch("controller.lib.onboarding.start_script", return_value={"success": True}):
            commit_onboarding("/dev/sda1", "ext4")

        mock_save.assert_called()

    def test_saves_primary_drive_to_config_when_mounts_empty(self, mock_docker_mode, tmp_path):
        """Should save primary drive to drives.mounts when config has no mounts."""
        media_dir = tmp_path / "wrolpi"

        with mock.patch("controller.lib.onboarding.get_media_directory", return_value=media_dir), \
             mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch("controller.lib.onboarding.mount_drive", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.add_fstab_entry", return_value={"success": True, "device": "UUID=abc-123"}), \
             mock.patch("controller.lib.onboarding.reload_config_from_drive", return_value=False), \
             mock.patch("controller.lib.onboarding.save_config"), \
             mock.patch("controller.lib.onboarding.get_config_value", return_value=[]), \
             mock.patch("controller.lib.onboarding.update_config") as mock_update, \
             mock.patch("controller.lib.onboarding.start_script", return_value={"success": True}):
            commit_onboarding("/dev/sda1", "ext4")

        mock_update.assert_called_once_with("drives.mounts", [{
            "device": "UUID=abc-123",
            "mount_point": str(media_dir),
            "fstype": "ext4",
            "options": "defaults",
        }])

    def test_does_not_overwrite_existing_mounts(self, mock_docker_mode, tmp_path):
        """Should not modify drives.mounts when config already has mounts."""
        media_dir = tmp_path / "wrolpi"
        existing_mounts = [{"device": "UUID=old", "mount_point": "/media/wrolpi", "fstype": "ext4"}]

        with mock.patch("controller.lib.onboarding.get_media_directory", return_value=media_dir), \
             mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch("controller.lib.onboarding.mount_drive", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.add_fstab_entry", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.reload_config_from_drive", return_value=True), \
             mock.patch("controller.lib.onboarding.save_config"), \
             mock.patch("controller.lib.onboarding.get_config_value", return_value=existing_mounts), \
             mock.patch("controller.lib.onboarding.update_config") as mock_update, \
             mock.patch("controller.lib.onboarding.start_script", return_value={"success": True}):
            commit_onboarding("/dev/sda1", "ext4")

        mock_update.assert_not_called()

    def test_mount_failure(self, mock_docker_mode, tmp_path):
        """Should return error when primary mount fails."""
        media_dir = tmp_path / "wrolpi"

        with mock.patch("controller.lib.onboarding.get_media_directory", return_value=media_dir), \
             mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch(
                 "controller.lib.onboarding.mount_drive",
                 return_value={"success": False, "error": "Device busy"},
             ):
            result = commit_onboarding("/dev/sda1", "ext4")

        assert result["success"] is False
        assert "Device busy" in result["error"]

    def test_secondary_mount_failure_continues(self, mock_docker_mode, tmp_path):
        """Secondary mount failure should not abort onboarding."""
        media_dir = tmp_path / "wrolpi"
        media_dir.mkdir()
        config_dir = media_dir / "config"
        config_dir.mkdir()

        config_data = {"drives": {"mounts": [
            {"device": "/dev/sdb1", "mount_point": "/media/backup", "fstype": "ext4"},
        ]}}
        (config_dir / "controller.yaml").write_text(yaml.dump(config_data))

        call_count = 0

        def mount_side_effect(device, mount_point, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"success": True}  # Primary mount succeeds
            return {"success": False, "error": "Not found"}  # Secondary fails

        with mock.patch("controller.lib.onboarding.get_media_directory", return_value=media_dir), \
             mock.patch("controller.lib.onboarding._cleanup_temp_mount"), \
             mock.patch("controller.lib.onboarding.mount_drive", side_effect=mount_side_effect), \
             mock.patch("controller.lib.onboarding.add_fstab_entry", return_value={"success": True}), \
             mock.patch("controller.lib.onboarding.reload_config_from_drive", return_value=True), \
             mock.patch("controller.lib.onboarding.save_config"), \
             mock.patch("controller.lib.onboarding.start_script", return_value={"success": True}):
            result = commit_onboarding("/dev/sda1", "ext4")

        assert result["success"] is True
        # Only primary mount should be in the list
        assert len(result["mounts"]) == 1


class TestCancelProbe:
    """Tests for cancel_probe."""

    def test_cancel_cleans_up(self, mock_docker_mode):
        """Cancel should clean up temp mount."""
        with mock.patch("controller.lib.onboarding._cleanup_temp_mount") as mock_cleanup:
            result = cancel_probe()

        assert result["success"] is True
        mock_cleanup.assert_called_once()
