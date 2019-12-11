from sanic_openapi import doc


class ChannelPostRequest:
    url = doc.String()
    name = doc.String(description='A short readable name', required=True)
    match_regex = doc.String(description='Regex that the video title will have to match')
    directory = doc.String(required=True)


class ChannelPutRequest:
    url = doc.String()
    name = doc.String()
    match_regex = doc.String()
    link = doc.String()
    directory = doc.String()


class SuccessResponse:
    success = doc.String()


class ChannelModel:
    id = doc.Integer()
    url = doc.String()
    name = doc.String()
    idempotency = doc.String()
    match_regex = doc.String()
    link = doc.String()
    directory = doc.String()
    info_json = doc.Dictionary
    info_date = doc.Date()


class ChannelResponse:
    channel = ChannelModel


class ChannelPostResponse:
    success = doc.String()


class ChannelsResponse:
    channels = doc.List(doc.Object(ChannelModel))


class DownloaderConfig:
    video_root_directory = doc.String()
    file_name_format = doc.String()


class JSONErrorResponse:
    error = doc.String()


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
    video_path_hash = doc.String()
    channel_id = doc.Integer()


class ChannelVideosResponse:
    videos = doc.List(Video)


class ChannelVideoResponse:
    video = Video


class VideoSearchRequest:
    search_str = doc.String(required=True)
    offset = doc.Integer()


class VideoSearchResponse:
    videos = doc.List(Video)


class PaginationQuery:
    offset = doc.Integer()
