from http import HTTPStatus

from sanic import Request, response, Blueprint
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from modules.map import lib, schema, search
from modules.map.pins import get_map_pins_config
from wrolpi.api_utils import json_response
from wrolpi.common import wrol_mode_check
from wrolpi.events import Events

map_bp = Blueprint('Map', '/api/map')


@map_bp.get('/files')
@openapi.description('List available PMTiles map files')
def get_files(_: Request):
    files = lib.get_pmtiles_files()
    return json_response(dict(files=files), HTTPStatus.OK)


@map_bp.delete('/files/<filename:str>')
@openapi.description('Delete a PMTiles map file')
@wrol_mode_check
async def delete_file(_: Request, filename: str):
    try:
        deleted = lib.delete_pmtiles_file(filename)
    except ValueError as e:
        return response.json({'error': str(e)}, HTTPStatus.BAD_REQUEST)

    if deleted:
        return response.empty()
    return response.json({'error': 'File not found'}, HTTPStatus.NOT_FOUND)


@map_bp.get('/subscribe')
@openapi.description('Get map catalog and current subscriptions')
def get_subscriptions(request: Request):
    catalog = lib.get_map_catalog()
    subscriptions = lib.get_map_subscriptions(request.ctx.session)
    return json_response(dict(catalog=catalog, subscriptions=subscriptions), HTTPStatus.OK)


@map_bp.post('/subscribe')
@openapi.description('Subscribe to a map region for automatic downloads')
@validate(schema.MapSubscribeRequest)
@wrol_mode_check
async def post_subscribe(request: Request, body: schema.MapSubscribeRequest):
    try:
        await lib.subscribe(request.ctx.session, body.name, body.region)
    except ValueError as e:
        return response.json({'error': str(e)}, HTTPStatus.BAD_REQUEST)

    Events.send_created(f'Map subscription created for {body.name}')
    return response.empty(HTTPStatus.CREATED)


@map_bp.delete('/subscribe/<region:str>')
@openapi.description('Unsubscribe from a map region')
@wrol_mode_check
async def delete_subscription(request: Request, region: str):
    try:
        await lib.unsubscribe(request.ctx.session, region)
    except ValueError as e:
        return response.json({'error': str(e)}, HTTPStatus.NOT_FOUND)

    return response.empty(HTTPStatus.NO_CONTENT)


@map_bp.get('/pins')
@openapi.description('Get all map pins')
def get_pins(_: Request):
    pins = get_map_pins_config().pins
    return json_response(dict(pins=pins), HTTPStatus.OK)


@map_bp.post('/pins')
@openapi.description('Add a map pin')
@validate(schema.MapPinRequest)
async def add_pin(_: Request, body: schema.MapPinRequest):
    pin = get_map_pins_config().add_pin(body.lat, body.lon, body.label, body.color)
    return json_response(dict(pin=pin), HTTPStatus.CREATED)


@map_bp.delete('/pins/<pin_id:int>')
@openapi.description('Delete a map pin by ID')
async def delete_pin(_: Request, pin_id: int):
    if get_map_pins_config().delete_pin(pin_id):
        return response.empty(HTTPStatus.NO_CONTENT)
    return response.json({'error': 'Pin not found'}, HTTPStatus.NOT_FOUND)


@map_bp.put('/pins/<pin_id:int>')
@openapi.description('Update a map pin by ID')
@validate(schema.MapPinUpdateRequest)
async def update_pin(_: Request, pin_id: int, body: schema.MapPinUpdateRequest):
    if get_map_pins_config().update_pin(pin_id, body.label, body.color):
        return response.empty(HTTPStatus.NO_CONTENT)
    return response.json({'error': 'Pin not found'}, HTTPStatus.NOT_FOUND)


@map_bp.get('/search')
@openapi.description('Search for places in map search indexes')
async def search_places(request: Request):
    q = request.args.get('q', '')
    if not q or len(q.strip()) < 1:
        return json_response({'error': 'Query parameter "q" is required'}, HTTPStatus.BAD_REQUEST)

    limit = int(request.args.get('limit', 10))
    lat = request.args.get('lat')
    lon = request.args.get('lon')

    if lat is not None:
        lat = float(lat)
    if lon is not None:
        lon = float(lon)

    results = search.search_places(q.strip(), limit=limit, lat=lat, lon=lon)
    return json_response(dict(results=results), HTTPStatus.OK)


@map_bp.get('/search/status')
@openapi.description('Get status of map search indexes')
async def get_search_status(_: Request):
    status = search.get_search_status()
    return json_response(status, HTTPStatus.OK)


@map_bp.post('/search/rebuild')
@openapi.description('Rebuild all map search indexes')
@wrol_mode_check
async def rebuild_search_indexes(_: Request):
    proc = search.rebuild_all_search_indexes()
    if proc:
        return json_response({'message': 'Search index rebuild started'}, HTTPStatus.ACCEPTED)
    return json_response({'error': 'No map directory found'}, HTTPStatus.NOT_FOUND)
