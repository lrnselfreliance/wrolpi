from sanic_openapi import doc


class ChannelPostRequest:
    url = doc.String()
    name = doc.String(description='A short readable name', required=True)
    match_regex = doc.String(description='Regex that the video title will have to match')
    directory = doc.String(required=True)
    mkdir = doc.Boolean()
    generate_posters = doc.Boolean()
    calculate_duration = doc.Boolean()
    download_frequency = doc.String()


class ChannelPutRequest:
    url = doc.String()
    name = doc.String()
    match_regex = doc.String()
    link = doc.String()
    directory = doc.String()
    generate_posters = doc.Boolean()
    calculate_duration = doc.Boolean()
    mkdir = doc.Boolean()
    download_frequency = doc.String()


class RefreshRequest:
    channel_name = doc.String()


class SuccessResponse:
    success = doc.String()


class ChannelModel:
    id = doc.Integer()
    url = doc.String()
    name = doc.String()
    match_regex = doc.String()
    link = doc.String()
    directory = doc.String()


class ChannelResponse:
    channel = ChannelModel


class ChannelPostResponse:
    success = doc.String()


class ChannelsChannelModel:
    id = doc.Integer()
    name = doc.String()
    link = doc.String()


class ChannelsResponse:
    channels = doc.List(doc.Object(ChannelsChannelModel))


class StreamResponse:
    success = doc.String()
    stream_url = doc.String()


class Video:
    id = doc.Integer()
    description_path = doc.String()
    ext = doc.String()
    poster_path = doc.String()
    source_id = doc.String()
    title = doc.String()
    upload_date = doc.Date()
    video_path = doc.String()
    name = doc.String()
    caption_path = doc.String()
    idempotency = doc.String()
    info_json_path = doc.String()
    channel_id = doc.Integer()


class VideoWithChannel:
    id = doc.Integer()
    description_path = doc.String()
    ext = doc.String()
    poster_path = doc.String()
    source_id = doc.String()
    title = doc.String()
    upload_date = doc.Date()
    video_path = doc.String()
    name = doc.String()
    caption_path = doc.String()
    idempotency = doc.String()
    info_json_path = doc.String()
    channel_id = doc.Integer()

    channel = ChannelModel


class ChannelVideosResponse:
    videos = doc.List(Video)


class ExtendedVideo(Video):
    info_json = doc.Object(dict)


class VideoResponse:
    video = ExtendedVideo


class VideoSearchRequest:
    search_str = doc.String()
    channel_link = doc.String()
    order_by = doc.String()
    offset = doc.Integer()
    limit = doc.Integer()
    filters = doc.List(doc.String())


class VideoSearchResponse:
    videos = doc.List(VideoWithChannel)
    tsquery = doc.String()


class PaginationQuery:
    offset = doc.Integer()


class DirectoriesRequest:
    search_str = doc.String(required=True)


class DirectoriesResponse:
    directories = doc.List(doc.String())


class FavoriteRequest:
    video_id = doc.Integer()
    favorite = doc.Boolean()


class FavoriteResponse:
    video_id = doc.Integer()
    favorite = doc.DateTime()


class WROLModeRequest:
    enabled = doc.Boolean(required=True)


class VideoStatistics:
    videos = doc.Integer()
    favorites = doc.Integer()
    week = doc.Integer()
    month = doc.Integer()
    year = doc.Integer()
    sum_duration = doc.Integer()
    sum_size = doc.Integer()
    max_size = doc.Integer()


class ChannelStatistics:
    channels = doc.Integer()


class VideosStatisticsResponse:
    videos = VideoStatistics
    channels = ChannelStatistics


class CensoredVideoRequest:
    limit = doc.Integer()
    offset = doc.Integer()


class CensoredVideoResponse:
    videos = doc.List(VideoWithChannel)
