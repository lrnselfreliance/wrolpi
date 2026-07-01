from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FlasherSearchRequest:
    # Only return firmware built for this chip (e.g. "ESP32-S2").  Null returns all ESP firmware.
    chip: Optional[str] = None
    # Case-insensitive partial match against the file path.
    path: Optional[str] = None
    limit: Optional[int] = 1000


@dataclass
class FlasherSaveConfigRequest:
    # The name of the saved configuration (added, or replaced if the name already exists).
    name: str
    # The firmware files to flash: [{path, address, name, size}, ...].
    files: List[dict] = field(default_factory=list)
    erase_all: bool = False
