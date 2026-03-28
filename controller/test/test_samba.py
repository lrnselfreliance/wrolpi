"""
Unit tests for controller.lib.samba module.
"""

import subprocess
from unittest import mock

from controller.lib.samba import (
    SambaStatus,
    _generate_smb_conf,
    add_share,
    apply_samba_from_config,
    get_samba_status,
    get_samba_status_dict,
    remove_share,
)


class TestGetSambaStatus:
    """Tests for get_samba_status function."""

    def test_returns_unavailable_in_docker_mode(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            assert get_samba_status() == SambaStatus.unavailable

    def test_returns_running_when_active(self):
        mock_result = mock.Mock()
        mock_result.stdout = "active\n"
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", return_value=mock_result):
                assert get_samba_status() == SambaStatus.running

    def test_returns_stopped_when_inactive(self):
        mock_result = mock.Mock()
        mock_result.stdout = "inactive\n"
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", return_value=mock_result):
                assert get_samba_status() == SambaStatus.stopped

    def test_returns_unavailable_when_systemctl_not_found(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
                assert get_samba_status() == SambaStatus.unavailable

    def test_returns_unknown_on_timeout(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
                assert get_samba_status() == SambaStatus.unknown


class TestGetSambaStatusDict:
    """Tests for get_samba_status_dict function."""

    def test_returns_expected_fields(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            result = get_samba_status_dict()
            assert "enabled" in result
            assert "available" in result
            assert "shares" in result

    def test_unavailable_in_docker(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            result = get_samba_status_dict()
            assert result["available"] is False
            assert result["reason"] is not None


class TestGenerateSmbConf:
    """Tests for _generate_smb_conf function."""

    def test_generates_global_section(self, reset_runtime_config):
        conf = _generate_smb_conf()
        assert "[global]" in conf
        assert "workgroup = WORKGROUP" in conf
        assert "map to guest = Bad User" in conf

    def test_generates_share_sections(self, reset_runtime_config):
        from controller.lib.config import update_config
        update_config("samba.shares", [
            {"name": "TestShare", "path": "/media/wrolpi/test", "read_only": True, "comment": "Test"},
        ])
        conf = _generate_smb_conf()
        assert "[TestShare]" in conf
        assert "path = /media/wrolpi/test" in conf
        assert "read only = yes" in conf
        assert "guest ok = yes" in conf

    def test_read_write_share(self, reset_runtime_config):
        from controller.lib.config import update_config
        update_config("samba.shares", [
            {"name": "Writable", "path": "/media/wrolpi", "read_only": False, "comment": ""},
        ])
        conf = _generate_smb_conf()
        assert "read only = no" in conf

    def test_empty_shares_produces_global_only(self, reset_runtime_config):
        conf = _generate_smb_conf()
        assert "[global]" in conf
        # No share sections.
        lines = conf.split("\n")
        sections = [l for l in lines if l.startswith("[") and l != "[global]"]
        assert len(sections) == 0


class TestAddShare:
    """Tests for add_share function."""

    def test_fails_in_docker_mode(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            result = add_share("test", "/media/wrolpi")
            assert result["success"] is False

    def test_rejects_invalid_name(self, reset_runtime_config):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            result = add_share("test/bad", "/media/wrolpi")
            assert result["success"] is False
            assert "alphanumeric" in result["error"]

    def test_rejects_path_outside_media_dir(self, reset_runtime_config, test_directory):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.samba.get_media_directory", return_value=test_directory):
                result = add_share("test", "/tmp")
                assert result["success"] is False
                assert "must be under" in result["error"]

    def test_rejects_nonexistent_path(self, reset_runtime_config, test_directory):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.samba.get_media_directory", return_value=test_directory):
                result = add_share("test", str(test_directory / "nonexistent"))
                assert result["success"] is False
                assert "does not exist" in result["error"]

    def test_rejects_duplicate_name(self, reset_runtime_config, test_directory):
        from controller.lib.config import update_config
        update_config("samba.shares", [
            {"name": "existing", "path": str(test_directory), "read_only": True, "comment": ""},
        ])
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.samba.get_media_directory", return_value=test_directory):
                with mock.patch("controller.lib.samba.save_config"):
                    with mock.patch("controller.lib.samba._write_smb_conf", return_value={"success": True}):
                        result = add_share("Existing", str(test_directory))
                        assert result["success"] is False
                        assert "already exists" in result["error"]

    def test_adds_share_successfully(self, reset_runtime_config, test_directory):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.samba.get_media_directory", return_value=test_directory):
                with mock.patch("controller.lib.samba.save_config"):
                    with mock.patch("controller.lib.samba._write_smb_conf", return_value={"success": True}):
                        result = add_share("MyShare", str(test_directory), read_only=False, comment="My files")
                        assert result["success"] is True
                        assert result["share"]["name"] == "MyShare"
                        assert result["share"]["read_only"] is False


class TestRemoveShare:
    """Tests for remove_share function."""

    def test_removes_share(self, reset_runtime_config):
        from controller.lib.config import update_config
        update_config("samba.shares", [
            {"name": "test", "path": "/media/wrolpi", "read_only": True, "comment": ""},
        ])
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.samba.save_config"):
                with mock.patch("controller.lib.samba._write_smb_conf", return_value={"success": True}):
                    result = remove_share("test")
                    assert result["success"] is True

                    from controller.lib.config import get_config_value
                    assert len(get_config_value("samba.shares", [])) == 0

    def test_returns_error_for_missing_share(self, reset_runtime_config):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            result = remove_share("nonexistent")
            assert result["success"] is False
            assert "not found" in result["error"]


class TestApplySambaFromConfig:
    """Tests for apply_samba_from_config function."""

    def test_skips_in_docker_mode(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            with mock.patch("controller.lib.samba._write_smb_conf") as mock_write:
                apply_samba_from_config()
                mock_write.assert_not_called()

    def test_writes_config_when_shares_exist(self, reset_runtime_config):
        from controller.lib.config import update_config
        update_config("samba.shares", [
            {"name": "test", "path": "/media/wrolpi", "read_only": True, "comment": ""},
        ])
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.samba._write_smb_conf", return_value={"success": True}) as mock_write:
                apply_samba_from_config()
                mock_write.assert_called_once()

    def test_skips_when_no_shares(self, reset_runtime_config):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.samba._write_smb_conf") as mock_write:
                apply_samba_from_config()
                mock_write.assert_not_called()
