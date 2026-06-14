from http import HTTPStatus

from wrolpi.errors import APIError


class UnknownInventory(APIError):
    code = 'UNKNOWN_INVENTORY'
    summary = 'No inventory with that slug exists'
    status_code = HTTPStatus.NOT_FOUND


class InvalidFieldSchema(APIError):
    code = 'INVALID_FIELD_SCHEMA'
    summary = 'The inventory field schema is invalid'
    status_code = HTTPStatus.BAD_REQUEST


class InventoryConflict(APIError):
    code = 'INVENTORY_CONFLICT'
    summary = 'The inventory was modified since it was loaded'
    status_code = HTTPStatus.CONFLICT
