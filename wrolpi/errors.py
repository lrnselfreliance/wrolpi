from http import HTTPStatus

from sanic import SanicException


class APIError(SanicException):
    code = 'APIError'
    summary = 'No summary defined'
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR


class UnknownDirectory(APIError):
    code = 'UNKNOWN_DIRECTORY'
    summary = 'The directory does not exist.'
    status_code = HTTPStatus.NOT_FOUND


class UnknownFile(APIError):
    code = 'UNKNOWN_FILE'
    summary = 'The file does not exist.'
    status_code = HTTPStatus.NOT_FOUND


class SearchEmpty(APIError):
    code = 'SEARCH_EMPTY'
    summary = 'Search is empty, search_str must have content.'
    status_code = HTTPStatus.BAD_REQUEST


class ValidationError(APIError):
    code = 'VALIDATION_ERROR'
    summary = 'Could not validate the contents of the request'
    status_code = HTTPStatus.BAD_REQUEST


class InvalidOrderBy(ValidationError):
    code = 'INVALID_ORDER_BY'
    summary = 'Invalid order_by'
    status_code = HTTPStatus.BAD_REQUEST


class WROLModeEnabled(APIError):
    code = 'WROL_MODE_ENABLED'
    summary = 'This method is disabled while WROL Mode is enabled.'
    status_code = HTTPStatus.FORBIDDEN


class InvalidDownload(APIError):
    code = 'INVALID_DOWNLOAD'
    summary = 'The URL cannot be downloaded.'
    status_code = HTTPStatus.BAD_REQUEST


class UnknownDownload(APIError):
    code = 'UNKNOWN_DOWNLOAD'
    summary = 'The Download cannot be found.'
    status_code = HTTPStatus.NOT_FOUND


class UnrecoverableDownloadError(APIError):
    code = 'UNRECOVERABLE_DOWNLOAD_ERROR'
    summary = 'Download experienced an error which cannot be recovered.  Download will be deleted.'
    status_code = HTTPStatus.BAD_REQUEST


class InvalidFile(APIError):
    code = 'INVALID_FILE'
    summary = 'File does not exist or is a directory'
    status_code = HTTPStatus.BAD_REQUEST


class NativeOnly(APIError):
    code = 'NATIVE_ONLY'
    summary = 'This functionality is only supported outside a docker container'
    status_code = HTTPStatus.BAD_REQUEST


class HotspotError(APIError):
    code = 'HOTSPOT_ERROR'
    summary = 'Updating/accessing Hotspot encountered an error'
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR


class LogLevelError(APIError):
    code = 'LOG_LEVEL_ERROR'
    summary = 'Log level is invalid'
    status_code = HTTPStatus.BAD_REQUEST


class UnknownArchive(APIError):
    code = 'UNKNOWN_ARCHIVE'
    summary = 'Unable to find the archive'
    status_code = HTTPStatus.NOT_FOUND


class UnknownTag(APIError):
    code = 'UNKNOWN_TAG'
    summary = 'Unable to find the tag'
    status_code = HTTPStatus.NOT_FOUND


class UsedTag(APIError):
    code = 'USED_TAG'
    summary = 'Tag is being used'
    status_code = HTTPStatus.BAD_REQUEST


class InvalidTag(APIError):
    code = 'INVALID_TAG'
    summary = 'Tag is not allowed'
    status_code = HTTPStatus.BAD_REQUEST


class FileGroupIsTagged(APIError):
    code = 'FILE_GROUP_IS_TAGGED'
    summary = 'FileGroup is tagged'
    status_code = HTTPStatus.CONFLICT


class FileGroupAlreadyTagged(APIError):
    code = 'FILE_GROUP_ALREADY_TAGGED'
    summary = 'FileGroup is already tagged with this Tag'
    status_code = HTTPStatus.CONFLICT


class FileUploadFailed(APIError):
    code = 'FILE_UPLOAD_FAILED'
    summary = 'Failed to upload file'
    status_code = HTTPStatus.BAD_REQUEST


class FileConflict(APIError):
    code = 'FILE_CONFLICT'
    summary = 'File/directory already exists'
    status_code = HTTPStatus.CONFLICT


class HotspotPasswordTooShort(APIError):
    code = 'HOTSPOT_PASSWORD_TOO_SHORT'
    summary = 'Hotspot password must be at least 8 characters'
    status_code = HTTPStatus.BAD_REQUEST


class ShutdownFailed(APIError):
    code = 'SHUTDOWN_FAILED'
    summary = 'Unable to shutdown the WROLPi'
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR


class InvalidConfig(APIError):
    code = 'INVALID_CONFIG'
    summary = 'Config is invalid'
    status_code = HTTPStatus.BAD_REQUEST


class NoPrimaryFile(APIError):
    code = 'NO_PRIMARY_FILE'
    summary = 'Could not find a primary file in the provided group'
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR


class InvalidDatetime(APIError):
    code = 'INVALID_DATETIME'
    summary = 'Unable to parse a datetime string'
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR


class InvalidDirectory(APIError):
    code = 'INVALID_DIRECTORY'
    summary = 'Directory is not valid or impossible'
    status_code = HTTPStatus.BAD_REQUEST


class RefreshConflict(APIError):
    code = 'REFRESH_CONFLICT'
    summary = 'Not possible during file refresh'
    status_code = HTTPStatus.CONFLICT


class IgnoredDirectoryError(APIError):
    code = 'IGNORED_DIRECTORY_ERROR'
    summary = 'Directory is being ignored'
    status_code = HTTPStatus.BAD_REQUEST


class DownloadError(APIError):
    code = 'DOWNLOAD_ERROR'
    summary = 'Unable to complete download'
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
