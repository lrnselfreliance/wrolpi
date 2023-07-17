from http import HTTPStatus

from wrolpi.errors import APIError


class InvalidArchive(APIError):
    code = 'INVALID_ARCHIVE'
    summary = 'The archive is invalid.  See server logs.'
    status = HTTPStatus.BAD_REQUEST
