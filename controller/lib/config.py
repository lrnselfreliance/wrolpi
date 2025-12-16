"""
Configuration management for the Controller.

Controller uses code-defined defaults and optionally loads overrides
from controller.yaml on the WROLPi drive after it's mounted.
"""

import copy
import os
from pathlib import Path
from typing import Any

import yaml

from controller.defaults import DEFAULT_CONFIG

# Path to config file on the WROLPi drive
CONFIG_PATH_ON_DRIVE = Path("/media/wrolpi/config/controller.yaml")

# Runtime config - starts as defaults, updated after drive mount
_runtime_config: dict = copy.deepcopy(DEFAULT_CONFIG)


def get_config() -> dict:
    """Get the current runtime configuration."""
    return _runtime_config


def get_config_value(key: str, default: Any = None) -> Any:
    """Get a specific config value by dot-notation key (e.g., 'drives.auto_mount')."""
    keys = key.split(".")
    value = _runtime_config
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return default
    return value


def is_docker_mode() -> bool:
    """Check if running in Docker container."""
    return os.environ.get("DOCKERIZED", "").lower() == "true"


# Raspberry Pi detection
RPI_DEVICE_PATH = Path('/proc/device-tree/model')
_RPI_DEVICE_MODEL_CONTENTS = RPI_DEVICE_PATH.read_text() if RPI_DEVICE_PATH.is_file() else None


def is_rpi4() -> bool:
    """Check if running on Raspberry Pi 4."""
    return 'Raspberry Pi 4' in _RPI_DEVICE_MODEL_CONTENTS if _RPI_DEVICE_MODEL_CONTENTS else False


def is_rpi5() -> bool:
    """Check if running on Raspberry Pi 5."""
    return 'Raspberry Pi 5' in _RPI_DEVICE_MODEL_CONTENTS if _RPI_DEVICE_MODEL_CONTENTS else False


def is_rpi() -> bool:
    """Check if running on any Raspberry Pi."""
    return is_rpi4() or is_rpi5()


def get_media_directory() -> Path:
    """Get the media directory path."""
    return Path(os.environ.get("MEDIA_DIRECTORY", "/media/wrolpi"))


def is_primary_drive_mounted() -> bool:
    """Check if the primary WROLPi drive is mounted."""
    return Path("/media/wrolpi/config").exists()


def reload_config_from_drive() -> bool:
    """
    Load config from the mounted WROLPi drive and merge with defaults.
    Called after the primary drive is mounted.

    Returns True if config was loaded, False if no config file found.
    """
    global _runtime_config

    if not CONFIG_PATH_ON_DRIVE.exists():
        # No config file on drive - keep defaults
        return False

    try:
        with open(CONFIG_PATH_ON_DRIVE) as f:
            drive_config = yaml.safe_load(f) or {}
    except (IOError, yaml.YAMLError) as e:
        # Failed to load - keep defaults
        print(f"Warning: Failed to load controller.yaml: {e}")
        return False

    # Deep merge: drive_config overrides defaults
    _runtime_config = _deep_merge(copy.deepcopy(DEFAULT_CONFIG), drive_config)
    return True


def save_config() -> None:
    """
    Save current runtime config to the WROLPi drive.
    Only saves the diff from defaults to keep the file clean.
    If config matches defaults, removes the config file.
    """
    if not is_primary_drive_mounted():
        raise RuntimeError("Cannot save config: primary drive not mounted")

    # Calculate diff from defaults
    diff = _get_config_diff(_runtime_config, DEFAULT_CONFIG)

    if not diff:
        # Config matches defaults - remove config file if it exists
        if CONFIG_PATH_ON_DRIVE.exists():
            CONFIG_PATH_ON_DRIVE.unlink()
        return

    CONFIG_PATH_ON_DRIVE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH_ON_DRIVE, "w") as f:
        yaml.dump(diff, f, default_flow_style=False, sort_keys=False)


def update_config(key: str, value: Any) -> None:
    """
    Update a config value by dot-notation key.
    Does not automatically save - call save_config() after updates.
    """
    keys = key.split(".")
    config = _runtime_config

    # Navigate to parent of target key
    for k in keys[:-1]:
        if k not in config:
            config[k] = {}
        config = config[k]

    # Set the value
    config[keys[-1]] = value


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dicts. Override values take precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _get_config_diff(current: dict, default: dict) -> dict:
    """Get the difference between current config and defaults."""
    diff = {}
    for key, value in current.items():
        if key not in default:
            diff[key] = value
        elif isinstance(value, dict) and isinstance(default.get(key), dict):
            nested_diff = _get_config_diff(value, default[key])
            if nested_diff:
                diff[key] = nested_diff
        elif value != default.get(key):
            diff[key] = value
    return diff
