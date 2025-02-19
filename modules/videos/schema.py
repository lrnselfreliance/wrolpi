from dataclasses import dataclass, field
from typing import List, Optional

from modules.videos.video.lib import DEFAULT_VIDEO_ORDER, VIDEO_QUERY_LIMIT
from wrolpi.errors import ValidationError


@dataclass
class ChannelPostRequest:
    name: str
    directory: str
    calculate_duration: Optional[bool] = None
    download_missing_data: Optional[bool] = True
    generate_posters: Optional[bool] = None
    source_id: Optional[str] = None
    tag_name: Optional[str] = None
    url: Optional[str] = None

    def __post_init__(self):
        self.name = self.name.strip() or None
        self.directory = self.directory.strip() or None
        self.url = self.url.strip() if self.url else None
        self.source_id = self.source_id.strip() if self.source_id else None


@dataclass
class ChannelPutRequest:
    calculate_duration: Optional[bool] = None
    directory: Optional[str] = None
    download_missing_data: Optional[bool] = True
    generate_posters: Optional[bool] = None
    mkdir: Optional[bool] = None
    name: Optional[str] = None
    url: Optional[str] = None

    def __post_init__(self):
        self.name = self.name.strip() or None
        self.directory = self.directory.strip() or None
        self.url = self.url.strip() if self.url else None


@dataclass
class ChannelTagRequest:
    tag_name: Optional[str] = None
    directory: Optional[str] = None

    def __post_init__(self):
        if self.directory and self.directory.startswith('/'):
            raise ValidationError('Directory must be relative to media directory')


@dataclass
class ChannelTagInfoRequest:
    channel_id: Optional[int] = None
    tag_name: Optional[str] = None


@dataclass
class ChannelDownloadRequest:
    url: str
    frequency: int
    settings: dict = field(default_factory=dict)

    def __post_init__(self):
        self.url = self.url.strip()
        if not self.url:
            raise ValidationError('url cannot be empty')

        # Validate settings contents.  Remove empty values.
        from wrolpi.schema import DownloadSettings
        self.settings = {k: v for k, v in DownloadSettings(**self.settings).__dict__.items() if v not in ([], None)}


@dataclass
class RefreshRequest:
    channel_name: str


@dataclass
class ChannelModel:
    id: int
    url: str
    name: str
    directory: str


@dataclass
class ChannelResponse:
    channel = ChannelModel


@dataclass
class ChannelPostResponse:
    success: str


@dataclass
class ChannelsChannelModel:
    id: int
    name: str


@dataclass
class ChannelsResponse:
    channels: List[ChannelsChannelModel]


@dataclass
class StreamResponse:
    success: str
    stream_url: str


@dataclass
class Video:
    id: int
    description_path: str
    ext: str
    poster_path: str
    source_id: str
    title: str
    video_path: str
    name: str
    caption_path: str
    idempotency: str
    info_json_path: str
    channel_id: int


@dataclass
class VideoWithChannel:
    id: int
    description_path: str
    ext: str
    poster_path: str
    source_id: str
    title: str
    video_path: str
    name: str
    caption_path: str
    idempotency: str
    info_json_path: str
    channel_id: int

    channel = ChannelModel


@dataclass
class ExtendedVideo(Video):
    info_json: dict


@dataclass
class VideoResponse:
    file_group = ExtendedVideo
    prev = ExtendedVideo
    next = ExtendedVideo


@dataclass
class VideoCommentsResponse:
    comments: list[dict]


@dataclass
class VideoCaptionsResponse:
    captions: str


@dataclass
class VideoSearchRequest:
    search_str: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    offset: Optional[int] = None
    limit: Optional[int] = VIDEO_QUERY_LIMIT
    order_by: Optional[str] = DEFAULT_VIDEO_ORDER
    channel_id: Optional[int] = None
    tag_names: List[str] = field(default_factory=list)
    headline: bool = False


@dataclass
class VideoSearchResponse:
    videos: List[VideoWithChannel]
    tsquery: str


@dataclass
class PaginationQuery:
    offset: int


@dataclass
class TagRequest:
    video_id: int
    tag_name: str


@dataclass
class WROLModeRequest:
    enabled: bool


@dataclass
class VideoStatistics:
    videos: int
    week: int
    month: int
    year: int
    sum_duration: int
    sum_size: int
    max_size: int
    have_comments: int
    missing_comments: int
    failed_comments: int


@dataclass
class ChannelStatistics:
    channels: int
    tagged_channels: int


@dataclass
class VideosStatisticsResponse:
    videos = VideoStatistics
    channels = ChannelStatistics


@dataclass
class CensoredVideoRequest:
    limit: int
    offset: int


@dataclass
class CensoredVideoResponse:
    videos: List[VideoWithChannel]


@dataclass
class ChannelSearchRequest:
    tag_names: List[str] = field(default_factory=list)


@dataclass
class VideoFileFormatRequest:
    video_file_format: str
