"""
WROL Mode detection for WROLPi Controller.

WROL Mode (Without Rule of Law) is an emergency mode that restricts
persistent configuration changes.
"""

from pathlib import Path

from controller.lib.config import get_media_directory


def get_wrol_mode_flag_path() -> Path:
    """Get the path to the WROL Mode flag file."""
    return get_media_directory() / "config" / ".wrol_mode"


def is_wrol_mode() -> bool:
    """
    Check if WROL Mode is active.

    WROL Mode is indicated by the presence of a flag file.
    This file is created/deleted by the API when the user toggles WROL Mode.
    """
    return get_wrol_mode_flag_path().exists()


def require_normal_mode(operation: str) -> None:
    """
    Raise an error if WROL Mode is active.

    Use this to guard persistent operations that shouldn't be
    allowed during emergencies.

    Args:
        operation: Description of the operation being attempted

    Raises:
        PermissionError: If WROL Mode is active
    """
    if is_wrol_mode():
        raise PermissionError(
            f"Cannot {operation} while WROL Mode is active. "
            "Disable WROL Mode to make persistent changes."
        )
