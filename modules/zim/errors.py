from http import HTTPStatus

from wrolpi.errors import APIError


class UnknownZim(APIError):
    code = 'UNKNOWN_ZIM'
    summary = 'Failed to find the Zim'
    status_code = HTTPStatus.NOT_FOUND


class UnknownZimEntry(APIError):
    code = 'UNKNOWN_ZIM_ENTRY'
    summary = 'Failed to find the Zim entry at that path'
    status_code = HTTPStatus.NOT_FOUND


class UnknownZimTagEntry(APIError):
    code = 'UNKNOWN_ZIM_TAG_ENTRY'
    summary = 'Failed to find the TagZimEntry'
    status_code = HTTPStatus.NOT_FOUND


class UnknownZimSubscription(APIError):
    code = 'UNKNOWN_ZIM_SUBSCRIPTION'
    summary = 'Failed to find the ZimSubscription'
    status_code = HTTPStatus.NOT_FOUND
