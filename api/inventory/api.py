from sanic import Blueprint, response
from sanic.request import Request

from .inventory import get_inventory_by_category

NAME = 'inventory'

api_bp = Blueprint('Inventory', url_prefix='/inventory')


@api_bp.get('/')
def inventory_get(request: Request):
    summary = get_inventory_by_category()
    return response.json(dict(summary=summary))
