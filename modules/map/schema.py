from dataclasses import dataclass


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
    lat: float
    lon: float
    label: str
    color: str = "red"


@dataclass
class MapPinUpdateRequest:
    label: str = None
    color: str = None
