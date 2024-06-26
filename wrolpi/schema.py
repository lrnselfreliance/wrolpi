from dataclasses import dataclass, field
from typing import Optional, List

from wrolpi.errors import InvalidDownload, ValidationError


@dataclass
class SettingsObject:
    media_directory: str


@dataclass
class SettingsResponse:
    config: SettingsObject


@dataclass
class SettingsRequest:
    archive_directory: Optional[str] = None
    download_on_startup: Optional[bool] = None
    download_timeout: Optional[int] = None
    hotspot_device: Optional[str] = None
    hotspot_on_startup: Optional[bool] = None
    hotspot_password: Optional[str] = None
    hotspot_ssid: Optional[str] = None
    hotspot_status: Optional[bool] = None
    ignore_outdated_zims: Optional[bool] = None
    log_level: Optional[int] = None
    map_directory: Optional[str] = None
    media_directory: Optional[str] = None
    throttle_on: Optional[bool] = None
    throttle_on_startup: Optional[bool] = None
    videos_directory: Optional[str] = None
    wrol_mode: Optional[bool] = None
    zims_directory: Optional[str] = None


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
class DownloadSettings:
    depth: Optional[int] = None
    destination: Optional[str] = None
    excluded_urls: Optional[str] = None
    max_pages: Optional[int] = None
    suffix: Optional[str] = None
    tag_names: List[str] = field(default_factory=lambda: list())
    title_exclude: str = None
    title_include: str = None

    def __post_init__(self):
        from wrolpi.common import get_media_directory
        self.tag_names = [i.strip() for i in self.tag_names] if self.tag_names else []
        self.excluded_urls = [i.strip() for i in self.excluded_urls.split(',')] if self.excluded_urls else None
        self.destination = str(get_media_directory() / self.destination) if self.destination else None
        if self.suffix and not self.suffix.startswith('.'):
            raise ValidationError('suffix must start with .')


@dataclass
class DownloadRequest:
    urls: List[str]
    downloader: str
    frequency: Optional[int] = None
    sub_downloader: Optional[str] = None
    settings: Optional[dict] = field(default_factory=lambda: dict())
    download_metadata_only: Optional[bool] = False

    def __post_init__(self):
        urls = [j for i in self.urls if (j := i.strip())]
        if not urls:
            raise InvalidDownload(f'urls cannot be empty')
        # Get unique URLs, preserve order.
        self.urls = list(dict.fromkeys(urls))

        # Validate settings contents.  Remove empty values.
        self.settings = {k: v for k, v in DownloadSettings(**self.settings).__dict__.items() if v not in ([], None)}


@dataclass
class JSONErrorResponse:
    error: str


@dataclass
class EventsRequest:
    after: Optional[str] = None


@dataclass
class TagRequest:
    name: str
    color: str


@dataclass
class DeleteTagRequest:
    name: str


@dataclass
class NotifyRequest:
    message: str
    url: str = None


@dataclass
class VINDecoderRequest:
    vin_number: str


@dataclass
class VIN:
    country: str
    manufacturer: str
    region: str
    years: str
    body: str = None
    engine: str = None
    model: str = None
    plant: str = None
    transmission: str = None
    serial: str = None

    def __json__(self) -> dict:
        d = dict(
            country=self.country,
            manufacturer=self.manufacturer,
            region=self.region,
            years=self.years,
            body=self.body,
            engine=self.engine,
            model=self.model,
            plant=self.plant,
            transmission=self.transmission,
            serial=self.serial,
        )
        return d


@dataclass
class VINDecoderResponse:
    vin: VIN


@dataclass
class SearchSuggestionsRequest:
    search_str: Optional[str] = None
    order_by_video_count: bool = True


@dataclass
class SearchFileEstimateRequest:
    search_str: Optional[str] = None
    mimetypes: List[str] = field(default_factory=lambda: list())
    tag_names: List[str] = field(default_factory=lambda: list())
    months: Optional[List[int]] = None
    from_year: Optional[int] = None
    to_year: Optional[int] = None
