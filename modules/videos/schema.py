from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from modules.videos.video.lib import DEFAULT_VIDEO_ORDER, VIDEO_QUERY_LIMIT


@dataclass
class ChannelPostRequest:
    name: str
    directory: str
    calculate_duration: Optional[bool] = None
    download_frequency: Optional[int] = None
    generate_posters: Optional[bool] = None
    match_regex: Optional[str] = None
    mkdir: Optional[bool] = None
    url: Optional[str] = None
    source_id: Optional[str] = None

    def __post_init__(self):
        self.name = self.name.strip() or None
        self.directory = self.directory.strip() or None
        self.url = self.url.strip() if self.url else None
        self.source_id = self.source_id.strip() if self.source_id else None


@dataclass
class ChannelPutRequest:
    calculate_duration: Optional[bool] = None
    directory: Optional[str] = None
    download_frequency: Optional[int] = None
    generate_posters: Optional[bool] = None
    match_regex: Optional[str] = None
    mkdir: Optional[bool] = None
    name: Optional[str] = None
    url: Optional[str] = None

    def __post_init__(self):
        self.name = self.name.strip() or None
        self.directory = self.directory.strip() or None
        self.url = self.url.strip() if self.url else None
        self.match_regex = None if self.match_regex in ('None', '') else self.match_regex


@dataclass
class RefreshRequest:
    channel_name: str


@dataclass
class ChannelModel:
    id: int
    url: str
    name: str
    match_regex: str
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
    upload_date: date
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
    upload_date: date
    video_path: str
    name: str
    caption_path: str
    idempotency: str
    info_json_path: str
    channel_id: int

    channel = ChannelModel


@dataclass
class ChannelVideosResponse:
    videos: List[Video]


@dataclass
class ExtendedVideo(Video):
    info_json: dict


@dataclass
class VideoResponse:
    file = ExtendedVideo
    prev = ExtendedVideo
    next = ExtendedVideo


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


@dataclass
class ChannelStatistics:
    channels: int


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
