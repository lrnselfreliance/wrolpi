from http import HTTPStatus

from wrolpi.errors import APIError


class UnknownRepo(APIError):
    code = 'UNKNOWN_REPO'
    summary = 'Unable to find the repo'
    status_code = HTTPStatus.NOT_FOUND


class InvalidRepo(APIError):
    code = 'INVALID_REPO'
    summary = 'The repo is invalid'
    status_code = HTTPStatus.BAD_REQUEST


class RepoConflict(APIError):
    code = 'REPO_CONFLICT'
    summary = 'The repo conflicts with an existing repo'
    status_code = HTTPStatus.CONFLICT
