"""
Unit tests for controller.lib.config module.
"""
import copy

import pytest
import yaml

from controller.lib.config import (
    get_config,
    get_config_value,
    is_docker_mode,
    is_primary_drive_mounted,
    reload_config_from_drive,
    save_config,
    update_config,
    _deep_merge,
    _get_config_diff,
)


class TestGetConfig:
    """Tests for get_config function."""

    def test_get_config_returns_dict(self, reset_runtime_config):
        """get_config should return a dictionary."""
        config = get_config()
        assert isinstance(config, dict)

    def test_get_config_has_default_keys(self, reset_runtime_config):
        """get_config should have all default keys."""
        config = get_config()
        assert "port" in config
        assert "media_directory" in config
        assert "drives" in config
        assert "managed_services" in config
        assert "hotspot" in config
        assert "throttle" in config

    def test_get_config_default_port(self, reset_runtime_config):
        """Default port should be 80."""
        config = get_config()
        assert config["port"] == 80


class TestGetConfigValue:
    """Tests for get_config_value function."""

    @pytest.mark.parametrize("key,expected", [
        ("port", 80),
        ("media_directory", "/media/wrolpi"),
        ("drives.auto_mount", True),
        ("hotspot.ssid", "WROLPi"),
        ("throttle.default_governor", "ondemand"),
    ])
    def test_get_value(self, reset_runtime_config, key, expected):
        """Should get values using dot notation for nested keys."""
        assert get_config_value(key) == expected

    @pytest.mark.parametrize("key,default,expected", [
        ("nonexistent", None, None),
        ("nonexistent", "fallback", "fallback"),
        ("drives.nonexistent", 42, 42),
        ("a.b.c.d.e", "default", "default"),
    ])
    def test_get_missing_value_returns_default(self, reset_runtime_config, key, default, expected):
        """Should return default for missing keys."""
        assert get_config_value(key, default) == expected


class TestIsDockerMode:
    """Tests for is_docker_mode function."""

    def test_docker_mode_false_when_not_set(self, mock_docker_mode):
        """Docker mode should be False when env var not set."""
        assert is_docker_mode() is False

    def test_docker_mode_true_when_set(self, mock_docker_mode_enabled):
        """Docker mode should be True when DOCKERIZED=true."""
        assert is_docker_mode() is True


class TestIsPrimaryDriveMounted:
    """Tests for is_primary_drive_mounted function."""

    def test_drive_mounted_when_controller_yaml_exists(self, mock_config_path):
        """Should return True when controller.yaml exists."""
        mock_config_path.write_text("{}")
        assert is_primary_drive_mounted() is True

    def test_drive_not_mounted_when_controller_yaml_missing(self, mock_config_path):
        """Should return False when controller.yaml doesn't exist."""
        # mock_config_path points to a non-existent file by default
        assert is_primary_drive_mounted() is False

    def test_drive_not_mounted_when_only_config_dir_exists(self, test_config_directory, mock_config_path):
        """Should return False when config/ dir exists but controller.yaml doesn't."""
        # test_config_directory creates the config dir but not controller.yaml
        assert test_config_directory.exists()
        assert is_primary_drive_mounted() is False


class TestReloadConfigFromDrive:
    """Tests for reload_config_from_drive function."""

    def test_reload_returns_false_when_no_config_file(
            self, reset_runtime_config, mock_config_path
    ):
        """Should return False when controller.yaml doesn't exist."""
        result = reload_config_from_drive()
        assert result is False

    def test_reload_returns_true_when_config_exists(
            self, reset_runtime_config, mock_config_path
    ):
        """Should return True and load config when file exists."""
        # Write a test config
        mock_config_path.write_text(yaml.dump({"port": 9999}))

        result = reload_config_from_drive()
        assert result is True
        assert get_config_value("port") == 9999

    def test_reload_merges_with_defaults(
            self, reset_runtime_config, mock_config_path
    ):
        """Config from file should be merged with defaults."""
        # Write partial config - only override port
        mock_config_path.write_text(yaml.dump({"port": 8888}))

        reload_config_from_drive()

        # Port should be overridden
        assert get_config_value("port") == 8888
        # Other defaults should still exist
        assert get_config_value("media_directory") == "/media/wrolpi"
        assert get_config_value("drives.auto_mount") is True

    def test_reload_handles_invalid_yaml(
            self, reset_runtime_config, mock_config_path
    ):
        """Should return False and keep defaults for invalid YAML."""
        mock_config_path.write_text("invalid: yaml: content: [}")

        result = reload_config_from_drive()
        assert result is False
        # Should still have defaults
        assert get_config_value("port") == 80

    def test_reload_handles_empty_file(
            self, reset_runtime_config, mock_config_path
    ):
        """Should handle empty config file gracefully."""
        mock_config_path.write_text("")

        result = reload_config_from_drive()
        # Empty file is valid YAML (returns None), merged with defaults
        # File exists and was processed, so returns True
        assert result is True
        # Config should still have all defaults
        assert get_config_value("port") == 80


class TestSaveConfig:
    """Tests for save_config function."""

    def test_save_config_raises_when_config_dir_missing(
            self, reset_runtime_config, test_directory
    ):
        """Should raise RuntimeError when config directory doesn't exist."""
        from unittest import mock
        from pathlib import Path

        # Point CONFIG_PATH_ON_DRIVE to a non-existent directory
        fake_path = Path(str(test_directory)) / "nonexistent" / "controller.yaml"
        with mock.patch("controller.lib.config.CONFIG_PATH_ON_DRIVE", fake_path):
            with pytest.raises(RuntimeError, match="primary drive not mounted"):
                save_config()

    def test_save_config_creates_file(
            self, reset_runtime_config, mock_config_path, mock_drive_mounted
    ):
        """Should create config file when saving."""
        update_config("port", 9999)
        save_config()

        assert mock_config_path.exists()
        saved = yaml.safe_load(mock_config_path.read_text())
        assert saved["port"] == 9999

    def test_save_config_only_saves_diff(
            self, reset_runtime_config, mock_config_path, mock_drive_mounted
    ):
        """Should only save values that differ from defaults."""
        # Only change port
        update_config("port", 9999)
        save_config()

        saved = yaml.safe_load(mock_config_path.read_text())
        # Only port should be in the file
        assert saved == {"port": 9999}

    def test_save_config_writes_empty_when_matches_defaults(
            self, reset_runtime_config, mock_config_path, mock_drive_mounted
    ):
        """Should still write file when config matches defaults (marker behavior)."""
        # First create a config file with non-default value
        update_config("port", 9999)
        save_config()
        assert mock_config_path.exists()

        # Reset to default value
        update_config("port", 80)  # Default port
        save_config()

        # File should still exist (serves as marker that drive is set up)
        assert mock_config_path.exists()
        saved = yaml.safe_load(mock_config_path.read_text())
        assert saved == {} or saved is None

    def test_save_config_always_writes_file(
            self, reset_runtime_config, mock_config_path, mock_drive_mounted
    ):
        """Should always write controller.yaml even with default config."""
        # Runtime config matches defaults (no changes made)
        save_config()

        # File should exist as a marker
        assert mock_config_path.exists()


class TestUpdateConfig:
    """Tests for update_config function."""

    def test_update_simple_value(self, reset_runtime_config):
        """Should update simple top-level values."""
        update_config("port", 9999)
        assert get_config_value("port") == 9999

    def test_update_nested_value(self, reset_runtime_config):
        """Should update nested values using dot notation."""
        update_config("hotspot.ssid", "MyNetwork")
        assert get_config_value("hotspot.ssid") == "MyNetwork"

    def test_update_creates_nested_structure(self, reset_runtime_config):
        """Should create nested structure if it doesn't exist."""
        update_config("new.nested.key", "value")
        assert get_config_value("new.nested.key") == "value"


class TestDeepMerge:
    """Tests for _deep_merge helper function."""

    @pytest.mark.parametrize("base,override,expected", [
        # Flat dict merge
        ({"a": 1, "b": 2}, {"b": 3, "c": 4}, {"a": 1, "b": 3, "c": 4}),
        # Nested dict merge
        ({"a": {"x": 1, "y": 2}}, {"a": {"y": 3, "z": 4}}, {"a": {"x": 1, "y": 3, "z": 4}}),
        # Override replaces non-dict
        ({"a": {"x": 1}}, {"a": "string"}, {"a": "string"}),
    ])
    def test_merge_dicts(self, base, override, expected):
        """Should merge dictionaries correctly."""
        result = _deep_merge(base, override)
        assert result == expected

    def test_merge_does_not_modify_original(self):
        """Should not modify original dictionaries."""
        base = {"a": 1}
        override = {"b": 2}
        original_base = copy.deepcopy(base)
        _deep_merge(base, override)
        assert base == original_base


class TestGetConfigDiff:
    """Tests for _get_config_diff helper function."""

    @pytest.mark.parametrize("config,default,expected", [
        # Equal configs return empty
        ({"a": 1, "b": 2}, {"a": 1, "b": 2}, {}),
        # Changed values only
        ({"a": 1, "b": 3}, {"a": 1, "b": 2}, {"b": 3}),
        # New keys
        ({"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 2}, {"c": 3}),
        # Nested changes
        ({"a": {"x": 1, "y": 3}}, {"a": {"x": 1, "y": 2}}, {"a": {"y": 3}}),
    ])
    def test_get_config_diff(self, config, default, expected):
        """Should return only values that differ from defaults."""
        assert _get_config_diff(config, default) == expected
