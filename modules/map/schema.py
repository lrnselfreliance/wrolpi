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


@dataclass
class MapPinUpdateRequest:
    label: Optional[str] = None
    color: Optional[str] = None


@dataclass
class MapFalloutWindsRequest:
    # The places ([lat, lon]) the field of winds is to cover: the targets.
    places: list


@dataclass
class MapTargetsRequest:
    # The targets to save ([{lat, lon, label, weapon?, yield_kt?, fission_fraction?, id?}]), and the ids
    # of the saved targets they were started from.
    targets: list
    loaded_ids: list
