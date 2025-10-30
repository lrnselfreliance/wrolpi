"""
Collection Type Registry

This module provides a registry system for different collection types (domains, channels, etc.)
to register their own validators and behavior rules.
"""
from typing import Callable, Dict, Optional

from wrolpi.common import logger

logger = logger.getChild(__name__)

# Type alias for validator functions
ValidatorFunc = Callable[[str], bool]


class CollectionTypeRegistry:
    """
    Registry for collection type validators and rules.

    Allows different collection types to register their own validation logic,
    making the system extensible for future collection types.
    """

    def __init__(self):
        self._validators: Dict[str, ValidatorFunc] = {}
        self._descriptions: Dict[str, str] = {}

    def register(self, kind: str, validator: ValidatorFunc, description: str = ""):
        """
        Register a validator for a collection type.

        Args:
            kind: The collection kind (e.g., 'domain', 'channel')
            validator: Function that takes a name and returns True if valid
            description: Human-readable description of validation rules
        """
        if kind in self._validators:
            logger.warning(f"Overwriting existing validator for collection kind '{kind}'")

        self._validators[kind] = validator
        self._descriptions[kind] = description
        logger.debug(f"Registered validator for collection kind '{kind}'")

    def validate(self, kind: str, name: str) -> bool:
        """
        Validate a collection name for a given type.

        Args:
            kind: The collection kind
            name: The collection name to validate

        Returns:
            True if valid, False otherwise
            If no validator is registered for the kind, returns True (permissive)
        """
        if kind not in self._validators:
            logger.debug(f"No validator registered for kind '{kind}', allowing any name")
            return True

        return self._validators[kind](name)

    def get_description(self, kind: str) -> Optional[str]:
        """Get the validation description for a collection type."""
        return self._descriptions.get(kind)

    def is_registered(self, kind: str) -> bool:
        """Check if a validator is registered for a collection type."""
        return kind in self._validators


# Global registry instance
collection_type_registry = CollectionTypeRegistry()


# Domain validator
def validate_domain_name(name: str) -> bool:
    """
    Validate that a name is a valid domain format.

    A valid domain must:
    - Be a string
    - Contain at least one "." (e.g., "example.com")
    - Not start or end with "."

    Examples:
        Valid: "example.com", "sub.example.com", "a.b.c"
        Invalid: "example", "example.", ".example", "."

    Args:
        name: The domain name to validate

    Returns:
        True if valid domain format, False otherwise
    """
    if not isinstance(name, str) or not name:
        return False

    # Must contain at least one "."
    if '.' not in name:
        return False

    # Should not start or end with "."
    if name.startswith('.') or name.endswith('.'):
        return False

    return True


# Channel validator (permissive - allows any non-empty string)
def validate_channel_name(name: str) -> bool:
    """
    Validate that a name is valid for a channel.

    Channels are permissive and allow any non-empty string.

    Args:
        name: The channel name to validate

    Returns:
        True if valid (non-empty string), False otherwise
    """
    return isinstance(name, str) and len(name.strip()) > 0


# Register built-in collection types
collection_type_registry.register(
    'domain',
    validate_domain_name,
    'Domain must contain at least one "." and not start/end with "."'
)

collection_type_registry.register(
    'channel',
    validate_channel_name,
    'Channel name must be a non-empty string'
)
