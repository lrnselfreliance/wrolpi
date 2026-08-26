from http import HTTPStatus

from wrolpi.errors import APIError


class ControllerUnavailable(APIError):
    code = 'CONTROLLER_UNAVAILABLE'
    summary = 'The Controller did not answer, or answered with an error.'
    status_code = HTTPStatus.BAD_GATEWAY
