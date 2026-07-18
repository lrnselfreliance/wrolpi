"""
Unit tests for controller.lib.wrol_mode module.
"""

from unittest import mock

import pytest

from controller.lib.wrol_mode import (
    disable_wrol_mode,
    enable_wrol_mode,
    get_wrol_mode_flag_path,
    get_wrol_mode_status_dict,
    is_wrol_mode,
    require_normal_mode,
)


class TestGetWrolModeFlagPath:
    """Tests for get_wrol_mode_flag_path function."""

    def test_returns_path(self):
        """Should return a Path object."""
        from pathlib import Path
        result = get_wrol_mode_flag_path()
        assert isinstance(result, Path)

    def test_path_ends_with_wrol_mode(self):
        """Path should end with .wrol_mode."""
        result = get_wrol_mode_flag_path()
        assert result.name == ".wrol_mode"

    def test_path_is_in_config_directory(self):
        """Path should be in config directory."""
        result = get_wrol_mode_flag_path()
        assert result.parent.name == "config"


class TestIsWrolMode:
    """Tests for is_wrol_mode function."""

    def test_returns_false_when_file_does_not_exist(self, tmp_path):
        """Should return False when flag file doesn't exist."""
        with mock.patch(
                "controller.lib.wrol_mode.get_wrol_mode_flag_path",
                return_value=tmp_path / ".wrol_mode"
        ):
            assert is_wrol_mode() is False

    def test_returns_true_when_file_exists(self, tmp_path):
        """Should return True when flag file exists."""
        flag_file = tmp_path / ".wrol_mode"
        flag_file.touch()

        with mock.patch(
                "controller.lib.wrol_mode.get_wrol_mode_flag_path",
                return_value=flag_file
        ):
            assert is_wrol_mode() is True


class TestRequireNormalMode:
    """Tests for require_normal_mode function."""

    def test_does_not_raise_when_not_in_wrol_mode(self):
        """Should not raise when WROL mode is inactive."""
        with mock.patch("controller.lib.wrol_mode.is_wrol_mode", return_value=False):
            # Should not raise
            require_normal_mode("test operation")

    def test_raises_permission_error_when_in_wrol_mode(self):
        """Should raise PermissionError when WROL mode is active."""
        with mock.patch("controller.lib.wrol_mode.is_wrol_mode", return_value=True):
            with pytest.raises(PermissionError) as exc_info:
                require_normal_mode("save configuration")

            assert "save configuration" in str(exc_info.value)
            assert "WROL Mode" in str(exc_info.value)

    def test_error_message_includes_operation_name(self):
        """Error message should include the operation name."""
        with mock.patch("controller.lib.wrol_mode.is_wrol_mode", return_value=True):
            with pytest.raises(PermissionError) as exc_info:
                require_normal_mode("modify settings")

            assert "modify settings" in str(exc_info.value)


class TestIsWrolModeYamlPreference:
    """is_wrol_mode prefers wrolpi.yaml when the key is present."""

    def test_yaml_true_overrides_missing_flag(self, tmp_path, monkeypatch):
        media = tmp_path / "media"
        config_dir = media / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "wrolpi.yaml").write_text("wrol_mode: true\n")
        monkeypatch.setenv("MEDIA_DIRECTORY", str(media))
        # Clear any cached path assumptions — get_media_directory reads env
        assert is_wrol_mode() is True

    def test_yaml_false_overrides_flag(self, tmp_path, monkeypatch):
        media = tmp_path / "media"
        config_dir = media / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "wrolpi.yaml").write_text("wrol_mode: false\n")
        (config_dir / ".wrol_mode").touch()
        monkeypatch.setenv("MEDIA_DIRECTORY", str(media))
        assert is_wrol_mode() is False


class TestEnableDisableWrolMode:
    def test_enable_creates_flag_and_yaml(self, tmp_path, monkeypatch):
        media = tmp_path / "media"
        config_dir = media / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "wrolpi.yaml").write_text("timezone: UTC\n")
        monkeypatch.setenv("MEDIA_DIRECTORY", str(media))

        with mock.patch("controller.lib.wrol_mode._notify_main_api", return_value=None):
            result = enable_wrol_mode()

        assert result["success"] is True
        assert (config_dir / ".wrol_mode").exists()
        assert "wrol_mode: true" in (config_dir / "wrolpi.yaml").read_text()
        assert is_wrol_mode() is True

    def test_disable_removes_flag_and_yaml(self, tmp_path, monkeypatch):
        media = tmp_path / "media"
        config_dir = media / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "wrolpi.yaml").write_text("wrol_mode: true\n")
        (config_dir / ".wrol_mode").touch()
        monkeypatch.setenv("MEDIA_DIRECTORY", str(media))

        with mock.patch("controller.lib.wrol_mode._notify_main_api", return_value=None):
            result = disable_wrol_mode()

        assert result["success"] is True
        assert not (config_dir / ".wrol_mode").exists()
        text = (config_dir / "wrolpi.yaml").read_text()
        assert "wrol_mode: false" in text
        assert is_wrol_mode() is False

    def test_status_dict_shape(self, tmp_path, monkeypatch):
        media = tmp_path / "media"
        config_dir = media / "config"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("MEDIA_DIRECTORY", str(media))
        status = get_wrol_mode_status_dict()
        assert status["enabled"] is False
        assert status["available"] is True
        assert status["flag_file"] is False
        assert status["yaml_value"] is None
