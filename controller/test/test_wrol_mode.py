"""
Unit tests for controller.lib.wrol_mode module.
"""

from unittest import mock

import pytest

from controller.lib.wrol_mode import (
    get_wrol_mode_flag_path,
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
