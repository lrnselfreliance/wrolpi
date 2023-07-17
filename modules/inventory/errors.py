from http import HTTPStatus

from wrolpi.errors import APIError


class NoInventories(APIError):
    code = 'NO_INVENTORIES'
    summary = 'No Inventories'
    status = HTTPStatus.BAD_REQUEST


class InventoriesVersionMismatch(APIError):
    code = 'INVENTORIES_VERSION_MISMATCH'
    summary = 'Inventories version in the DB does not match the inventories config'
    status = HTTPStatus.BAD_REQUEST
