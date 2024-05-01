from http import HTTPStatus

from wrolpi.errors import APIError


class UnknownVideo(APIError):
    code = 'UNKNOWN_VIDEO'
    message = 'The video could not be found.'
    status_code = HTTPStatus.NOT_FOUND


class UnknownChannel(APIError):
    code = 'UNKNOWN_CHANNEL'
    message = 'The channel could not be found.'
    status_code = HTTPStatus.NOT_FOUND


class ChannelNameConflict(APIError):
    code = 'CHANNEL_NAME_CONFLICT'
    message = 'The channel name is already taken.'
    status_code = HTTPStatus.BAD_REQUEST


class ChannelURLConflict(APIError):
    code = 'CHANNEL_URL_CONFLICT'
    message = 'The URL is already used by another channel.'
    status_code = HTTPStatus.BAD_REQUEST


class ChannelDirectoryConflict(APIError):
    code = 'CHANNEL_DIRECTORY_CONFLICT'
    message = 'The directory is already used by another channel.'
    status_code = HTTPStatus.BAD_REQUEST


class ChannelSourceIdConflict(APIError):
    code = 'CHANNEL_SOURCE_ID_CONFLICT'
    message = 'Search is empty, search_str must have content.'
    status_code = HTTPStatus.BAD_REQUEST


class ChannelURLEmpty(APIError):
    code = 'CHANNEL_URL_EMPTY'
    message = 'This channel has no URL'
    status_code = HTTPStatus.BAD_REQUEST
