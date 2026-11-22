from dataclasses import dataclass
from typing import Optional


@dataclass
class MapSubscribeRequest:
    name: str
    region: str


@dataclass
class MapFileVisibleRequest:
    map_path: str
    visible: bool


@dataclass
class MapPinRequest:
    # A browser sends a whole number of degrees as an integer.
    lat: float | int
    lon: float | int
    label: str
    color: str = "red"
    # "pin", or "target": a likely detonation site, shown in the map's nuclear mode.
    kind: str = "pin"
    # A target's weapon: the key of a weapon the simulator offers (or "custom"), the yield (kt) of a
    # custom one, and the share of the yield from fission.
    weapon: Optional[str] = None
    yield_kt: Optional[float | int] = None
    fission_fraction: Optional[float | int] = None


@dataclass
class MapPinUpdateRequest:
    label: Optional[str] = None
    color: Optional[str] = None
    weapon: Optional[str] = None
    yield_kt: Optional[float | int] = None
    fission_fraction: Optional[float | int] = None


@dataclass
class MapFalloutWindsRequest:
    # A browser sends a whole number of degrees as an integer.
    lat: float | int
    lon: float | int


@dataclass
class MapTargetsWeaponRequest:
    # The key of a weapon the simulator offers (or "custom"), the yield (kt) of a custom one, and the
    # share of the yield from fission.
    weapon: str
    yield_kt: Optional[float | int] = None
    fission_fraction: Optional[float | int] = None
