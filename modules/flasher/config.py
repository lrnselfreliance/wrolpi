"""A YAML config storing the user's saved firmware flashing configurations.

Each saved configuration is a named set of firmware files (media-relative paths) and their flash offsets, plus
whether to erase the flash first.  This lets a user configure a multi-part flash once (e.g. a Meshtastic T-Deck:
firmware at 0x0, littlefs at 0xc90000) and re-load it later with one click.
"""
from dataclasses import dataclass, field
from typing import List

from wrolpi.common import ConfigFile, logger

logger = logger.getChild(__name__)


@dataclass
class FlasherConfigValidator:
    version: int = None
    configurations: list = field(default_factory=list)


class FlasherConfig(ConfigFile):
    file_name = 'flasher.yaml'
    default_config = dict(
        version=0,
        configurations=[],
    )
    validator = FlasherConfigValidator

    def import_config(self, file=None, send_events=False):
        super().import_config(file, send_events)
        # YAML-only config (no database); a successful read is a successful import.
        self.successful_import = True

    @property
    def configurations(self) -> List[dict]:
        return list(self._config.get('configurations', []))

    @configurations.setter
    def configurations(self, value: List[dict]):
        # ConfigFile.update() validates, stores, and triggers a background save.
        self.update({'configurations': value})

    def save_configuration(self, name: str, files: List[dict], erase_all: bool = False) -> dict:
        """Add or replace (by name) a saved configuration.  Returns the stored configuration."""
        name = (name or '').strip()
        if not name:
            raise ValueError('Configuration name is required')
        # Keep only the fields we persist for each file.
        stored_files = [
            dict(
                path=f.get('path'),
                address=f.get('address'),
                name=f.get('name'),
                size=f.get('size'),
            )
            for f in files
        ]
        configuration = dict(name=name, erase_all=bool(erase_all), files=stored_files)
        # Replace any existing configuration with the same name, then keep the list sorted by name.
        configurations = [c for c in self.configurations if c.get('name') != name]
        configurations.append(configuration)
        configurations.sort(key=lambda c: (c.get('name') or '').lower())
        self.configurations = configurations
        return configuration

    def delete_configuration(self, name: str) -> bool:
        """Delete a saved configuration by name.  Returns True if one was removed."""
        configurations = self.configurations
        remaining = [c for c in configurations if c.get('name') != name]
        if len(remaining) == len(configurations):
            return False
        self.configurations = remaining
        return True


FLASHER_CONFIG: FlasherConfig = FlasherConfig()

# Test override (see get_flasher_config).
TEST_FLASHER_CONFIG = None


def get_flasher_config() -> FlasherConfig:
    global TEST_FLASHER_CONFIG
    if isinstance(TEST_FLASHER_CONFIG, ConfigFile):
        return TEST_FLASHER_CONFIG
    return FLASHER_CONFIG
