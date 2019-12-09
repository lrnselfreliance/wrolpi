from sanic_openapi import doc


class ChannelRequest:
    url = doc.String()
    name = doc.String()
    match_regex = doc.String()
    link = doc.String()
    directory = doc.String()


class SettingsResponse:
    success = doc.String()


class ChannelModel:
    id = doc.Integer()


class ChannelResponse:
    channel = ChannelModel


class ChannelPostResponse:
    success = doc.String()


class ChannelsModel:
    channels = doc.List(doc.Object(ChannelModel))


class DownloaderConfig:
    video_root_directory = doc.String()
    file_name_format = doc.String()


class JSONErrorResponse:
    error = doc.String()


class StreamResponse:
    success = doc.String()
    stream_url = doc.String()
