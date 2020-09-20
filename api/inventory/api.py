from http import HTTPStatus

from sanic import Blueprint, response
from sanic.request import Request

from .inventory import get_inventory_by_category, get_inventory_by_name, get_items, save_item, delete_items, \
    get_inventories, save_inventory, delete_inventory, update_inventory, update_item, get_inventory_by_subcategory
from .schema import ItemPostRequest, InventoryPostRequest, InventoryPutRequest, ItemPutRequest
from ..common import validate_doc, json_response
from ..errors import ValidationError

NAME = 'inventory'

api_bp = Blueprint('Inventory', url_prefix='/inventory')


@api_bp.get('/')
def inventories_get(request: Request):
    inventories = get_inventories()
    return json_response(dict(inventories=inventories))


@api_bp.get('/<inventory_id:int>')
def inventory_get(request: Request, inventory_id: int):
    by_category = get_inventory_by_category(inventory_id)
    by_subcategory = get_inventory_by_subcategory(inventory_id)
    by_name = get_inventory_by_name(inventory_id)
    return json_response(dict(by_category=by_category, by_subcategory=by_subcategory, by_name=by_name))


@api_bp.post('/')
@validate_doc(
    'Save a new inventory',
    consumes=InventoryPostRequest,
)
def post_inventory(request: Request, data: dict):
    save_inventory(data)
    return response.empty(HTTPStatus.CREATED)


@api_bp.put('/<inventory_id:int>')
@validate_doc(
    'Update an inventory',
    consumes=InventoryPutRequest,
)
def put_inventory(request: Request, inventory_id: int, data: dict):
    update_inventory(inventory_id, data)
    return response.empty()


@api_bp.delete('/<inventory_id:int>')
def inventory_delete(request: Request, inventory_id: int):
    delete_inventory(inventory_id)
    return response.empty()


@api_bp.get('/<inventory_id:int>/item')
@validate_doc(
    "Get all items from an inventory.",
)
def items_get(request: Request, inventory_id: int):
    items = get_items(inventory_id)
    return json_response({'items': items})


@api_bp.post('/<inventory_id:int>/item')
@validate_doc(
    "Save an item into it's inventory.",
    consumes=ItemPostRequest,
)
def post_item(request: Request, inventory_id: int, data: dict):
    save_item(inventory_id, data)
    return response.empty()


@api_bp.put('/item/<item_id:int>')
@validate_doc(
    "Update an item",
    consumes=ItemPutRequest,
)
def put_item(request: Request, item_id: int, data: dict):
    update_item(item_id, data)
    return response.empty()


@api_bp.delete('/item/<item_ids:[0-9,]+>')
@validate_doc(
    'Delete items from an inventory.',
)
def item_delete(request: Request, item_ids: str):
    try:
        item_ids = [int(i) for i in item_ids.split(',')]
    except ValueError:
        raise ValidationError('Could not parse item_ids')

    delete_items(item_ids)
    return response.empty()
