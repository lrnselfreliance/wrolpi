from http import HTTPStatus

from wrolpi.errors import APIError


class UnknownVideo(APIError):
    code = 'UNKNOWN_VIDEO'
    summary = 'The video could not be found.'
    status = HTTPStatus.NOT_FOUND


class UnknownChannel(APIError):
    code = 'UNKNOWN_CHANNEL'
    summary = 'The channel could not be found.'
    status = HTTPStatus.NOT_FOUND


class ChannelNameConflict(APIError):
    code = 'CHANNEL_NAME_CONFLICT'
    summary = 'The channel name is already taken.'
    status = HTTPStatus.BAD_REQUEST


class ChannelURLConflict(APIError):
    code = 'CHANNEL_URL_CONFLICT'
    summary = 'The URL is already used by another channel.'
    status = HTTPStatus.BAD_REQUEST


class ChannelDirectoryConflict(APIError):
    code = 'CHANNEL_DIRECTORY_CONFLICT'
    summary = 'The directory is already used by another channel.'
    status = HTTPStatus.BAD_REQUEST


class ChannelSourceIdConflict(APIError):
    code = 'CHANNEL_SOURCE_ID_CONFLICT'
    summary = 'Search is empty, search_str must have content.'
    status = HTTPStatus.BAD_REQUEST


class ChannelURLEmpty(APIError):
    code = 'CHANNEL_URL_EMPTY'
    summary = 'This channel has no URL'
    status = HTTPStatus.BAD_REQUEST
