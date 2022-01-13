from dataclasses import dataclass
from typing import List


@dataclass
class SettingsObject:
    media_directory: str


@dataclass
class SettingsResponse:
    config: SettingsObject


@dataclass
class SettingsRequest:
    media_directory: str
    wrol_mode: bool
    timezone: str


@dataclass
class RegexRequest:
    regex: str


@dataclass
class RegexResponse:
    regex: str
    valid: bool


@dataclass
class EchoResponse:
    form: dict
    headers: dict
    json: str
    method: str


@dataclass
class EventObject:
    name: str
    is_set: str


@dataclass
class EventsResponse:
    events: List[EventObject]


@dataclass
class DownloadRequest:
    urls: str
    downloader: str


@dataclass
class JSONErrorResponse:
    error: str
