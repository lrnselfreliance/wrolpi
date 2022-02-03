from http import HTTPStatus

from sanic import response
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi.common import run_after, remove_dict_value_whitespace
from wrolpi.errors import ValidationError
from wrolpi.root_api import get_blueprint, json_response
from .common import get_inventory_by_category, get_inventory_by_subcategory, get_inventory_by_name, \
    save_inventories_file
from .inventory import get_items, save_item, delete_items, \
    get_inventories, save_inventory, delete_inventory, update_inventory, update_item, get_categories, get_brands
from .schema import ItemPostRequest, InventoryPostRequest, InventoryPutRequest, ItemPutRequest

NAME = 'inventory'

bp = get_blueprint('Inventory', '/api/inventory')


@bp.get('/categories')
def _get_categories(_: Request):
    categories = get_categories()
    return json_response(dict(categories=categories))


@bp.get('/brands')
def _get_brands(_: Request):
    brands = get_brands()
    return json_response(dict(brands=brands))


@bp.get('/')
def inventories_get(_: Request):
    inventories = get_inventories()
    return json_response(dict(inventories=inventories))


@bp.get('/<inventory_id:int>')
def inventory_get(_: Request, inventory_id: int):
    by_category = get_inventory_by_category(inventory_id)
    by_subcategory = get_inventory_by_subcategory(inventory_id)
    by_name = get_inventory_by_name(inventory_id)
    return json_response(dict(by_category=by_category, by_subcategory=by_subcategory, by_name=by_name))


@bp.post('/')
@openapi.definition(
    summary='Save a new inventory',
    body=InventoryPostRequest,
)
@validate(InventoryPostRequest)
@run_after(save_inventories_file)
def post_inventory(_: Request, data: dict):
    # Cleanup the whitespace.
    data = remove_dict_value_whitespace(data)

    save_inventory(data)
    return response.empty(HTTPStatus.CREATED)


@bp.put('/<inventory_id:int>')
@openapi.definition(
    summary='Update an inventory',
    body=InventoryPutRequest,
)
@validate(InventoryPutRequest)
@run_after(save_inventories_file)
def put_inventory(_: Request, inventory_id: int, data: dict):
    # Cleanup the whitespace.
    data = remove_dict_value_whitespace(data)

    update_inventory(inventory_id, data)
    return response.empty()


@bp.delete('/<inventory_id:int>')
@openapi.description('Delete an inventory.')
@run_after(save_inventories_file)
def inventory_delete(_: Request, inventory_id: int):
    delete_inventory(inventory_id)
    return response.empty()


@bp.get('/<inventory_id:int>/item')
@openapi.description('Get all items from an inventory.')
def items_get(_: Request, inventory_id: int):
    items = get_items(inventory_id)
    return json_response({'items': items})


@bp.post('/<inventory_id:int>/item')
@openapi.definition(
    summary="Save an item into it's inventory.",
    body=ItemPostRequest,
)
@validate(ItemPostRequest)
@run_after(save_inventories_file)
def post_item(_: Request, inventory_id: int, data: dict):
    # Cleanup the whitespace.
    data = remove_dict_value_whitespace(data)

    save_item(inventory_id, data)
    return response.empty()


@bp.put('/item/<item_id:int>')
@openapi.definition(
    summary='Update an item.',
    body=ItemPutRequest,
)
@validate(ItemPutRequest)
@run_after(save_inventories_file)
def put_item(_: Request, item_id: int, data: dict):
    # Cleanup the whitespace.
    data = remove_dict_value_whitespace(data)

    update_item(item_id, data)
    return response.empty()


@bp.delete('/item/<item_ids:[0-9,]+>')
@bp.delete('/item/<item_ids:int>')
@openapi.description('Delete items from an inventory.')
@run_after(save_inventories_file)
def item_delete(_: Request, item_ids: str):
    try:
        if isinstance(item_ids, int):
            item_ids = [item_ids, ]
        else:
            item_ids = [int(i) for i in item_ids.split(',')]
    except ValueError:
        raise ValidationError('Could not parse item_ids')

    delete_items(item_ids)
    return response.empty()
