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


class ValidationError(APIError):
    pass


class ChannelLinkConflict(APIError):
    pass


class BadFieldType(APIError):
    pass


class MissingRequiredField(APIError):
    pass


class ExcessJSONFields(APIError):
    pass


class NoBodyContents(APIError):
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
    ValidationError: {
        'code': next(error_codes),
        'message': 'Could not validate the contents of the request',
        'status': HTTPStatus.BAD_REQUEST,
    },
    ChannelLinkConflict: {
        'code': next(error_codes),
        'message': 'Channel link already used by another channel',
        'status': HTTPStatus.BAD_REQUEST,
    },
    BadFieldType: {
        'code': next(error_codes),
        'message': 'Field could not be converted to the required type',
        'status': HTTPStatus.BAD_REQUEST,
    },
    MissingRequiredField: {
        'code': next(error_codes),
        'message': 'Missing required field',
        'status': HTTPStatus.BAD_REQUEST,
    },
    ExcessJSONFields: {
        'code': next(error_codes),
        'message': 'Extra fields in request',
        'status': HTTPStatus.BAD_REQUEST,
    },
    NoBodyContents: {
        'code': next(error_codes),
        'message': 'No content in the body of the request',
        'status': HTTPStatus.BAD_REQUEST,
    },
}
