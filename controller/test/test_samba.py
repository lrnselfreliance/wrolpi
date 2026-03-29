"""
Unit tests for controller.lib.samba module.
"""

import subprocess
from unittest import mock

from controller.lib.samba import (
    SambaStatus,
    _generate_smb_conf,
    _get_smb_conf_path,
    _reload_samba,
    _start_samba,
    _stop_samba,
    add_share,
    apply_samba_from_config,
    get_samba_status,
    get_samba_status_dict,
    remove_share,
)


class TestGetSambaStatus:
    """Tests for get_samba_status function."""

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

    def test_docker_mode_returns_running(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
                with mock.patch("controller.lib.docker_services.get_container_status",
                                return_value={"status": "running"}):
                    assert get_samba_status() == SambaStatus.running

    def test_docker_mode_returns_stopped(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
                with mock.patch("controller.lib.docker_services.get_container_status",
                                return_value={"status": "stopped"}):
                    assert get_samba_status() == SambaStatus.stopped

    def test_docker_mode_unavailable_without_docker(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=False):
                assert get_samba_status() == SambaStatus.unavailable


class TestGetSambaStatusDict:
    """Tests for get_samba_status_dict function."""

    def test_returns_expected_fields(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=False):
                result = get_samba_status_dict()
                assert "enabled" in result
                assert "available" in result
                assert "shares" in result

    def test_unavailable_without_docker(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=False):
                result = get_samba_status_dict()
                assert result["available"] is False
                assert result["reason"] is not None


class TestGetSmbConfPath:
    """Tests for _get_smb_conf_path function."""

    def test_native_mode(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            assert str(_get_smb_conf_path()) == "/etc/samba/smb.conf"

    def test_docker_mode(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            path = _get_smb_conf_path()
            assert "config/smb.conf" in str(path)


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
        lines = conf.split("\n")
        sections = [l for l in lines if l.startswith("[") and l != "[global]"]
        assert len(sections) == 0


class TestReloadSamba:
    """Tests for _reload_samba function."""

    def test_native_mode_calls_smbcontrol(self):
        mock_result = mock.Mock()
        mock_result.stdout = "active\n"
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
                _reload_samba()
                calls = [str(c) for c in mock_run.call_args_list]
                assert any("smbcontrol" in c for c in calls)

    def test_docker_mode_restarts_container(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
                with mock.patch("controller.lib.docker_services.restart_container") as mock_restart:
                    _reload_samba()
                    mock_restart.assert_called_once_with("samba")


class TestStartStopSamba:
    """Tests for _start_samba and _stop_samba functions."""

    def test_start_native(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run") as mock_run:
                _start_samba()
                calls = [str(c) for c in mock_run.call_args_list]
                assert any("start" in c and "smbd" in c for c in calls)

    def test_stop_native(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("subprocess.run") as mock_run:
                _stop_samba()
                calls = [str(c) for c in mock_run.call_args_list]
                assert any("stop" in c and "smbd" in c for c in calls)

    def test_start_docker(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
                with mock.patch("controller.lib.docker_services.start_container") as mock_start:
                    _start_samba()
                    mock_start.assert_called_once_with("samba")

    def test_stop_docker(self):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=True):
            with mock.patch("controller.lib.docker_services.can_manage_containers", return_value=True):
                with mock.patch("controller.lib.docker_services.stop_container") as mock_stop:
                    _stop_samba()
                    mock_stop.assert_called_once_with("samba")


class TestAddShare:
    """Tests for add_share function."""

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

    def test_adds_share_and_starts_samba(self, reset_runtime_config, test_directory):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.samba.get_media_directory", return_value=test_directory):
                with mock.patch("controller.lib.samba.save_config"):
                    with mock.patch("controller.lib.samba._write_smb_conf", return_value={"success": True}):
                        with mock.patch("controller.lib.samba.get_samba_status", return_value=SambaStatus.stopped):
                            with mock.patch("controller.lib.samba._start_samba") as mock_start:
                                result = add_share("MyShare", str(test_directory))
                                assert result["success"] is True
                                mock_start.assert_called_once()

    def test_adds_share_reloads_if_already_running(self, reset_runtime_config, test_directory):
        with mock.patch("controller.lib.samba.is_docker_mode", return_value=False):
            with mock.patch("controller.lib.samba.get_media_directory", return_value=test_directory):
                with mock.patch("controller.lib.samba.save_config"):
                    with mock.patch("controller.lib.samba._write_smb_conf", return_value={"success": True}):
                        with mock.patch("controller.lib.samba.get_samba_status", return_value=SambaStatus.running):
                            with mock.patch("controller.lib.samba._reload_samba") as mock_reload:
                                result = add_share("MyShare", str(test_directory))
                                assert result["success"] is True
                                mock_reload.assert_called_once()


class TestRemoveShare:
    """Tests for remove_share function."""

    def test_removes_share(self, reset_runtime_config):
        from controller.lib.config import update_config
        update_config("samba.shares", [
            {"name": "test", "path": "/media/wrolpi", "read_only": True, "comment": ""},
            {"name": "other", "path": "/media/wrolpi", "read_only": True, "comment": ""},
        ])
        with mock.patch("controller.lib.samba.save_config"):
            with mock.patch("controller.lib.samba._write_smb_conf", return_value={"success": True}):
                with mock.patch("controller.lib.samba._reload_samba"):
                    result = remove_share("test")
                    assert result["success"] is True

                    from controller.lib.config import get_config_value
                    assert len(get_config_value("samba.shares", [])) == 1

    def test_stops_samba_when_last_share_removed(self, reset_runtime_config):
        from controller.lib.config import update_config
        update_config("samba.shares", [
            {"name": "last", "path": "/media/wrolpi", "read_only": True, "comment": ""},
        ])
        with mock.patch("controller.lib.samba.save_config"):
            with mock.patch("controller.lib.samba._write_smb_conf", return_value={"success": True}):
                with mock.patch("controller.lib.samba._stop_samba") as mock_stop:
                    result = remove_share("last")
                    assert result["success"] is True
                    mock_stop.assert_called_once()

    def test_returns_error_for_missing_share(self, reset_runtime_config):
        result = remove_share("nonexistent")
        assert result["success"] is False
        assert "not found" in result["error"]


class TestApplySambaFromConfig:
    """Tests for apply_samba_from_config function."""

    def test_starts_samba_when_shares_exist(self, reset_runtime_config):
        from controller.lib.config import update_config
        update_config("samba.shares", [
            {"name": "test", "path": "/media/wrolpi", "read_only": True, "comment": ""},
        ])
        with mock.patch("controller.lib.samba._write_smb_conf", return_value={"success": True}):
            with mock.patch("controller.lib.samba.get_samba_status", return_value=SambaStatus.stopped):
                with mock.patch("controller.lib.samba._start_samba") as mock_start:
                    apply_samba_from_config()
                    mock_start.assert_called_once()

    def test_stops_samba_when_no_shares(self, reset_runtime_config):
        with mock.patch("controller.lib.samba._write_smb_conf", return_value={"success": True}):
            with mock.patch("controller.lib.samba.get_samba_status", return_value=SambaStatus.running):
                with mock.patch("controller.lib.samba._stop_samba") as mock_stop:
                    apply_samba_from_config()
                    mock_stop.assert_called_once()

    def test_does_not_start_if_already_running(self, reset_runtime_config):
        from controller.lib.config import update_config
        update_config("samba.shares", [
            {"name": "test", "path": "/media/wrolpi", "read_only": True, "comment": ""},
        ])
        with mock.patch("controller.lib.samba._write_smb_conf", return_value={"success": True}):
            with mock.patch("controller.lib.samba.get_samba_status", return_value=SambaStatus.running):
                with mock.patch("controller.lib.samba._start_samba") as mock_start:
                    apply_samba_from_config()
                    mock_start.assert_not_called()

    def test_does_not_stop_if_already_stopped(self, reset_runtime_config):
        with mock.patch("controller.lib.samba._write_smb_conf", return_value={"success": True}):
            with mock.patch("controller.lib.samba.get_samba_status", return_value=SambaStatus.stopped):
                with mock.patch("controller.lib.samba._stop_samba") as mock_stop:
                    apply_samba_from_config()
                    mock_stop.assert_not_called()
