from dataclasses import dataclass
from typing import Optional


@dataclass
class FlasherSearchRequest:
    # Only return firmware built for this chip (e.g. "ESP32-S2").  Null returns all ESP firmware.
    chip: Optional[str] = None
    # Case-insensitive partial match against the file path.
    path: Optional[str] = None
    limit: Optional[int] = 1000
