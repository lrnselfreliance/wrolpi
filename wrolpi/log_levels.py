"""
Log level utilities.

IMPORTANT: Keep this module minimal with NO imports from wrolpi to avoid circular imports.
This module is imported very early by vars.py.
"""
import logging
import os
from pathlib import Path

TRACE_LEVEL = 5

LOG_LEVELS = {
    'critical': logging.CRITICAL,
    'warning': logging.WARNING,
    'info': logging.INFO,
    'debug': logging.DEBUG,
    'trace': TRACE_LEVEL,
}


def name_to_int(name: str) -> int:
    """Convert log level name to integer. Defaults to INFO for invalid names."""
    return LOG_LEVELS.get(str(name).lower(), logging.INFO)


def int_to_name(level: int) -> str:
    """Convert log level integer to name. Defaults to 'info' for invalid levels."""
    for name, value in LOG_LEVELS.items():
        if value == level:
            return name
    return 'info'


def get_log_level_from_env_or_config() -> int:
    """
    Get log level from environment variable or config file.

    Priority:
    1. LOG_LEVEL environment variable
    2. log_level in wrolpi.yaml config file
    3. Default to INFO

    NOTE: CLI flags are handled separately by main.py argparse and take highest priority.
    This function is called during vars.py import (very early), before argparse runs.
    """
    # 1. Environment variable (highest priority at this stage)
    if env_level := os.environ.get('LOG_LEVEL'):
        return name_to_int(env_level)

    # 2. Config file
    try:
        import yaml
        media_dir = Path(os.environ.get('MEDIA_DIRECTORY', '/media/wrolpi'))
        config_path = media_dir / 'config/wrolpi.yaml'
        if config_path.is_file():
            with open(config_path) as f:
                config = yaml.safe_load(f)
                if config and 'log_level' in config:
                    return name_to_int(config['log_level'])
    except Exception:
        pass  # Config doesn't exist or is invalid, use default

    # 3. Default
    return logging.INFO
