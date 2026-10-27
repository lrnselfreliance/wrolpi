from http import HTTPStatus

from wrolpi.errors import APIError


class UnknownInventory(APIError):
    code = 'UNKNOWN_INVENTORY'
    summary = 'No inventory with that slug exists'
    status_code = HTTPStatus.NOT_FOUND


class InventoryConflict(APIError):
    code = 'INVENTORY_CONFLICT'
    summary = 'The inventory was modified since it was loaded'
    status_code = HTTPStatus.CONFLICT
