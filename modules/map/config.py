from dataclasses import dataclass, field
from typing import List

from wrolpi.common import ConfigFile, logger

logger = logger.getChild(__name__)


@dataclass
class MapsConfigValidator:
    version: int = None
    ignored_files: list = field(default_factory=list)


class MapsConfig(ConfigFile):
    """Settings of the map files.

    `ignored_files` are PMTiles files (relative to the map directory) the map does not draw, offer as a layer, or
    search.  A file the config does not name is visible."""
    file_name = 'maps.yaml'
    default_config = dict(
        version=0,
        ignored_files=[],
    )
    validator = MapsConfigValidator

    @property
    def ignored_files(self) -> List[str]:
        return [str(i) for i in self._config.get('ignored_files') or []]

    def is_ignored(self, map_path: str) -> bool:
        return str(map_path) in self.ignored_files

    def set_ignored(self, map_path: str, ignored: bool) -> bool:
        """Ignore (or stop ignoring) a map file.  Returns True if this changed the config."""
        map_path = str(map_path)
        ignored_files = set(self.ignored_files)
        if (map_path in ignored_files) == ignored:
            return False
        if ignored:
            ignored_files.add(map_path)
        else:
            ignored_files.discard(map_path)
        # Saves the config in the background.
        self.update({'ignored_files': sorted(ignored_files)})
        return True


MAPS_CONFIG: MapsConfig = MapsConfig()

# Test override.
TEST_MAPS_CONFIG = None


def get_maps_config() -> MapsConfig:
    global TEST_MAPS_CONFIG
    if isinstance(TEST_MAPS_CONFIG, ConfigFile):
        return TEST_MAPS_CONFIG
    return MAPS_CONFIG

