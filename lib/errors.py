from http import HTTPStatus


class APIError(Exception):
    pass


class UnknownVideo(APIError):
    pass


class UnknownChannel(APIError):
    pass


class UnknownDirectory(APIError):
    pass


class UnknownFile(APIError):
    pass


class ChannelNameConflict(APIError):
    pass


class ChannelURLConflict(APIError):
    pass


class ChannelDirectoryConflict(APIError):
    pass


class SearchEmpty(APIError):
    pass


class UnknownCaptionFile(APIError):
    pass


def error_code_generator():
    code = 0
    while True:
        code += 1
        yield code


error_codes = error_code_generator()

API_ERRORS = {
    UnknownVideo: {
        'code': next(error_codes),
        'message': 'The video could not be found.',
        'status': HTTPStatus.NOT_FOUND,
    },
    UnknownChannel: {
        'code': next(error_codes),
        'message': 'The channel could not be found by its link.',
        'status': HTTPStatus.NOT_FOUND,
    },
    UnknownDirectory: {
        'code': next(error_codes),
        'message': 'The directory does not exist.',
        'status': HTTPStatus.NOT_FOUND,
    },
    UnknownFile: {
        'code': next(error_codes),
        'message': 'The file does not exist.',
        'status': HTTPStatus.NOT_FOUND,
    },
    ChannelNameConflict: {
        'code': next(error_codes),
        'message': 'The channel name is already taken.',
        'status': HTTPStatus.BAD_REQUEST,
    },
    ChannelURLConflict: {
        'code': next(error_codes),
        'message': 'The URL is already used by another channel.',
        'status': HTTPStatus.BAD_REQUEST,
    },
    ChannelDirectoryConflict: {
        'code': next(error_codes),
        'message': 'The directory is already used by another channel.',
        'status': HTTPStatus.BAD_REQUEST,
    },
    SearchEmpty: {
        'code': next(error_codes),
        'message': 'Search is empty, search_str must have content.',
        'status': HTTPStatus.BAD_REQUEST,
    },
    UnknownCaptionFile: {
        'code': next(error_codes),
        'message': 'The caption file could not be found',
        'status': HTTPStatus.NOT_FOUND,
    },
}
