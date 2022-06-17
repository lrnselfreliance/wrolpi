from dataclasses import dataclass
from typing import Optional


@dataclass
class SettingsObject:
    media_directory: str


@dataclass
class SettingsResponse:
    config: SettingsObject


@dataclass
class SettingsRequest:
    download_on_startup: Optional[bool] = None
    download_timeout: Optional[int] = None
    hotspot_device: Optional[str] = None
    hotspot_on_startup: Optional[bool] = None
    hotspot_password: Optional[str] = None
    hotspot_ssid: Optional[str] = None
    hotspot_status: Optional[bool] = None
    media_directory: Optional[str] = None
    throttle_on: Optional[bool] = None
    throttle_on_startup: Optional[bool] = None
    timezone: Optional[str] = None
    wrol_mode: Optional[bool] = None


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
class DownloadRequest:
    urls: str
    downloader: Optional[str] = None
    frequency: Optional[int] = None
    sub_downloader: Optional[str] = None


@dataclass
class JSONErrorResponse:
    error: str
