from marshmallow import Schema, fields


class ChannelSchema(Schema):
    url = fields.Str()
    name = fields.Str(required=True)
    match_regex = fields.Str()
    link = fields.Str()
    directory = fields.Str()


channel_schema = ChannelSchema()


class DownloaderConfig(Schema):
    video_root_directory = fields.Str(required=True)
    file_name_format = fields.Str(required=True)


downloader_config_schema = DownloaderConfig()
