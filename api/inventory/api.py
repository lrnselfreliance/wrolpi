from sanic import Blueprint, response
from sanic.request import Request

from .inventory import get_inventory_by_category, get_inventory_by_name, get_items, save_item, delete_items
from .schema import ItemPostRequest
from ..common import validate_doc
from ..errors import ValidationError

NAME = 'inventory'

api_bp = Blueprint('Inventory', url_prefix='/inventory')


@api_bp.get('/<inventory_id:int>')
def inventory_get(request: Request, inventory_id: int):
    by_category = get_inventory_by_category()
    by_name = get_inventory_by_name()
    return response.json(dict(by_category=by_category, by_name=by_name))


@api_bp.get('/<inventory_id:int>/item')
@validate_doc(
    "Get all items from an inventory.",
)
def items_get(request: Request, inventory_id: int):
    items = get_items()
    return response.json({'items': items})


@api_bp.post('/<inventory_id:int>/item')
@validate_doc(
    "Save an item into it's inventory.",
    consumes=ItemPostRequest,
)
def post_item(request: Request, inventory_id: int, data: dict):
    save_item(data)
    return response.empty()


@api_bp.delete('/<inventory_id:int>/item/<item_ids:[0-9,]+>')
@validate_doc(
    'Delete items from an inventory.',
)
def item_delete(request: Request, inventory_id: int, item_ids: str):
    try:
        item_ids = [int(i) for i in item_ids.split(',')]
    except ValueError:
        raise ValidationError('Could not parse item_ids')

    delete_items(item_ids)
    return response.empty()
