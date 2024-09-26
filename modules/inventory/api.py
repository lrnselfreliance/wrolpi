from http import HTTPStatus

from sanic import response, Blueprint
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from modules.inventory import common, inventory, schema
from wrolpi.api_utils import json_response
from wrolpi.common import run_after, recursive_map
from wrolpi.errors import ValidationError

NAME = 'inventory'

inventory_bp = Blueprint('Inventory', '/api/inventory')


@inventory_bp.get('/categories')
def get_categories(_: Request):
    categories = inventory.get_categories()
    return json_response(dict(categories=categories))


@inventory_bp.get('/brands')
def get_brands(_: Request):
    brands = inventory.get_brands()
    return json_response(dict(brands=brands))


@inventory_bp.get('/')
def get_inventories(_: Request):
    inventories = inventory.get_inventories()
    return json_response(dict(inventories=inventories))


@inventory_bp.get('/<inventory_id:int>')
def get_inventory(_: Request, inventory_id: int):
    by_category = common.get_inventory_by_category(inventory_id)
    by_subcategory = common.get_inventory_by_subcategory(inventory_id)
    by_name = common.get_inventory_by_name(inventory_id)
    return json_response(dict(by_category=by_category, by_subcategory=by_subcategory, by_name=by_name))


@inventory_bp.post('/')
@openapi.definition(
    summary='Save a new inventory',
    body=schema.InventoryPostRequest,
)
@validate(schema.InventoryPostRequest)
@run_after(common.save_inventories_config)
def post_inventory(_: Request, body: schema.InventoryPostRequest):
    data = remove_whitespace(body.__dict__)

    inventory.save_inventory(data)
    return response.empty(HTTPStatus.CREATED)


@inventory_bp.put('/<inventory_id:int>')
@openapi.definition(
    summary='Update an inventory',
    body=schema.InventoryPutRequest,
)
@validate(schema.InventoryPutRequest)
@run_after(common.save_inventories_config)
def put_inventory(_: Request, inventory_id: int, body: schema.InventoryPutRequest):
    data = remove_whitespace(body.__dict__)

    inventory.update_inventory(inventory_id, data)
    return response.empty()


@inventory_bp.delete('/<inventory_id:int>')
@openapi.description('Delete an inventory.')
@run_after(common.save_inventories_config)
def inventory_delete(_: Request, inventory_id: int):
    inventory.delete_inventory(inventory_id)
    return response.empty()


@inventory_bp.get('/<inventory_id:int>/item')
@openapi.description('Get all items from an inventory.')
def items_get(_: Request, inventory_id: int):
    items = inventory.get_items(inventory_id)
    return json_response({'items': items})


@inventory_bp.post('/<inventory_id:int>/item')
@openapi.definition(
    summary="Save an item into it's inventory.",
    body=schema.ItemPostRequest,
)
@validate(schema.ItemPostRequest)
@run_after(common.save_inventories_config)
def post_item(_: Request, inventory_id: int, body: schema.ItemPostRequest):
    data = remove_whitespace(body.__dict__)

    inventory.save_item(inventory_id, data)
    return response.empty()


@inventory_bp.put('/item/<item_id:int>')
@openapi.definition(
    summary='Update an item.',
    body=schema.ItemPutRequest,
)
@validate(schema.ItemPutRequest)
@run_after(common.save_inventories_config)
def put_item(_: Request, item_id: int, body: schema.ItemPutRequest):
    data = remove_whitespace(body.__dict__)

    inventory.update_item(item_id, data)
    return response.empty()


@inventory_bp.delete('/item/<item_ids:[0-9,]+>', name='item_delete_many')
@inventory_bp.delete('/item/<item_ids:int>', name='item_delete_one')
@openapi.description('Delete items from an inventory.')
@run_after(common.save_inventories_config)
def item_delete(_: Request, item_ids: str):
    try:
        if isinstance(item_ids, int):
            item_ids = [item_ids, ]
        else:
            item_ids = [int(i) for i in item_ids.split(',')]
    except ValueError:
        raise ValidationError('Could not parse item_ids')

    inventory.delete_items(item_ids)
    return response.empty()


def remove_whitespace(obj):
    return recursive_map(obj, lambda i: i.strip() if hasattr(i, 'strip') else i)
