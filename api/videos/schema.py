from sanic_openapi import doc


class ChannelPostRequest:
    url = doc.String()
    name = doc.String(description='A short readable name', required=True)
    match_regex = doc.String(description='Regex that the video title will have to match')
    directory = doc.String(required=True)
    mkdir = doc.Boolean()
    generate_thumbnails = doc.Boolean()
    calculate_duration = doc.Boolean()


class ChannelPutRequest:
    url = doc.String()
    name = doc.String()
    match_regex = doc.String()
    link = doc.String()
    directory = doc.String()
    generate_thumbnails = doc.Boolean()
    calculate_duration = doc.Boolean()


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
    search_str = doc.String(required=True)
    offset = doc.Integer()


class VideoSearchResponse:
    videos = doc.List(VideoWithChannel)
    tsquery = doc.String()


class PaginationQuery:
    offset = doc.Integer()


class SettingsObject:
    media_directory = doc.String()


class SettingsResponse:
    config = doc.Object(SettingsObject)


class SettingsRequest:
    media_directory = doc.String()


class RegexRequest:
    regex = doc.String()


class RegexResponse:
    regex = doc.String()
    valid = doc.Boolean()


class DirectoriesRequest:
    search_str = doc.String(required=True)


class DirectoriesResponse:
    directories = doc.List(doc.String())


class EventObject:
    name = doc.String()
    is_set = doc.Boolean()


class EventsResponse:
    events = doc.List(EventObject)
