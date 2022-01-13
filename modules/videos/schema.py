from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional


@dataclass
class ChannelPostRequest:
    url: str
    name: str
    match_regex: str
    directory: str
    mkdir: bool
    generate_posters: bool
    calculate_duration: bool
    download_frequency: str


@dataclass
class ChannelPutRequest:
    url: str
    name: str
    match_regex: str
    link: str
    directory: str
    generate_posters: bool
    calculate_duration: bool
    mkdir: bool
    download_frequency: str


@dataclass
class RefreshRequest:
    channel_name: str


@dataclass
class SuccessResponse:
    success: str


@dataclass
class ChannelModel:
    id: int
    url: str
    name: str
    match_regex: str
    link: str
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
    link: str


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
    video = ExtendedVideo


@dataclass
class VideoSearchRequest:
    search_str: str
    filters: Optional[List[str]] = field(default_factory=list)
    offset: Optional[int] = None
    limit: Optional[int] = None
    order_by: Optional[str] = None
    channel_link: Optional[str] = None


@dataclass
class VideoSearchResponse:
    videos: List[VideoWithChannel]
    tsquery: str


@dataclass
class PaginationQuery:
    offset: int


@dataclass
class DirectoriesRequest:
    search_str: str


@dataclass
class DirectoriesResponse:
    directories: List[str]


@dataclass
class FavoriteRequest:
    video_id: int
    favorite: bool


@dataclass
class FavoriteResponse:
    video_id: int
    favorite: datetime


@dataclass
class WROLModeRequest:
    enabled: bool


@dataclass
class VideoStatistics:
    videos: int
    favorites: int
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
