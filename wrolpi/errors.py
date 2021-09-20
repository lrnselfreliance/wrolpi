from http import HTTPStatus


# TODO remove service-specific errors


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


class InvalidOrderBy(ValidationError):
    pass


class WROLModeEnabled(APIError):
    pass


class ChannelURLEmpty(APIError):
    pass


class InvalidOTP(APIError):
    pass


class InvalidPlaintext(APIError):
    pass


class InvalidCiphertext(APIError):
    pass


class NoFrequency(APIError):
    pass


class NoInventories(APIError):
    pass


class InventoriesVersionMismatch(APIError):
    pass


class InvalidTimezone(APIError):
    pass


error_codes = iter(range(1, 1000))

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
    InvalidOrderBy: {
        'code': next(error_codes),
        'message': 'Invalid order_by',
        'status': HTTPStatus.BAD_REQUEST,
    },
    WROLModeEnabled: {
        'code': next(error_codes),
        'message': 'This method is disabled while WROL Mode is enabled.',
        'status': HTTPStatus.FORBIDDEN,
    },
    ChannelURLEmpty: {
        'code': next(error_codes),
        'message': 'This channel has no URL',
        'status': HTTPStatus.BAD_REQUEST,
    },
    InvalidOTP: {
        'code': next(error_codes),
        'message': 'OTP has invalid characters',
        'status': HTTPStatus.BAD_REQUEST,
    },
    InvalidPlaintext: {
        'code': next(error_codes),
        'message': 'Plaintext has invalid characters',
        'status': HTTPStatus.BAD_REQUEST,
    },
    InvalidCiphertext: {
        'code': next(error_codes),
        'message': 'Ciphertext has invalid characters',
        'status': HTTPStatus.BAD_REQUEST,
    },
    NoFrequency: {
        'code': next(error_codes),
        'message': 'Channel does not have a frequency',
        'status': HTTPStatus.BAD_REQUEST,
    },
    NoInventories: {
        'code': next(error_codes),
        'message': 'No Inventories',
        'status': HTTPStatus.BAD_REQUEST,
    },
    InventoriesVersionMismatch: {
        'code': next(error_codes),
        'message': 'Inventories version in the DB does not match the inventories config',
        'status': HTTPStatus.BAD_REQUEST,
    },
    InvalidTimezone: {
        'code': next(error_codes),
        'message': 'Invalid timezone',
        'status': HTTPStatus.BAD_REQUEST,
    },
}
