from http import HTTPStatus

from sanic import response, Blueprint
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from modules.inventory import schema
from modules.inventory.common import get_inventory_configs
from modules.inventory.catalog import get_catalog_config, save_catalog_items
from modules.inventory.errors import UnknownInventory
from wrolpi.api_utils import json_response

NAME = 'inventory'

inventory_bp = Blueprint('Inventory', '/api/inventory')

# Inventory is config-only.  The frontend loads every inventory once (GET /), derives everything (selected items,
# summary, location suggestions, ration data) client-side, and persists whole inventories (PUT /<slug>).  There are
# deliberately no granular item/field/suggestion endpoints.


@inventory_bp.get('/')
@openapi.description('Get every inventory in full (fields and items).')
def get_inventories(_: Request):
    inventories = get_inventory_configs().all_inventories()
    return json_response(dict(inventories=inventories))


@inventory_bp.post('/')
@openapi.definition(
    summary='Create a new inventory',
    body=schema.InventoryPostRequest,
)
@validate(schema.InventoryPostRequest)
def post_inventory(_: Request, body: schema.InventoryPostRequest):
    inventory = get_inventory_configs().create_inventory(body.name, body.type or 'food')
    return json_response(dict(inventory=inventory), HTTPStatus.CREATED)


# Shared food catalog (static routes, declared before the dynamic /<slug> routes).
@inventory_bp.get('/catalog')
@openapi.description('Get the shared food catalog entries.')
def get_catalog(_: Request):
    return json_response(dict(catalog=get_catalog_config().items))


@inventory_bp.put('/catalog')
@openapi.description('Replace the shared food catalog (whole-list save).')
def put_catalog(request: Request):
    items = (request.json or {}).get('items', [])
    return json_response(dict(catalog=save_catalog_items(items)))


@inventory_bp.put('/<slug:str>')
@openapi.description('Replace an inventory (name / fields / items) in one request.')
def put_inventory(request: Request, slug: str):
    if get_inventory_configs().get_inventory(slug) is None:
        raise UnknownInventory(f'No inventory: {slug}')
    body = request.json or {}
    expected_version = body.get('version')
    inventory = get_inventory_configs().save_inventory(slug, body, expected_version=expected_version)
    return json_response(dict(inventory=inventory))


@inventory_bp.delete('/<slug:str>')
@openapi.description('Delete an inventory.')
def inventory_delete(_: Request, slug: str):
    if get_inventory_configs().get_inventory(slug) is None:
        raise UnknownInventory(f'No inventory: {slug}')
    get_inventory_configs().delete_inventory(slug)
    return response.empty()
