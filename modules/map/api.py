import asyncio
from http import HTTPStatus

from sanic import Request, response, Blueprint
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from modules.map import export, export_job, lib, quads, schema, search, winds
from modules.map.pins import get_map_pins_config
from modules.map.sheet import legend_as_sent
from wrolpi import flags
from wrolpi.api_utils import json_response
from wrolpi.common import wrol_mode_check
from wrolpi.events import Events

map_bp = Blueprint('Map', '/api/map')


@map_bp.get('/files')
@openapi.description('List available PMTiles map files')
def get_files(_: Request):
    files = lib.get_pmtiles_files()
    return json_response(dict(files=files), HTTPStatus.OK)


@map_bp.delete('/files/<filename:path>')
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


@map_bp.post('/files/visible')
@openapi.description('Show a PMTiles map file on the map, or ignore it')
@validate(schema.MapFileVisibleRequest)
@wrol_mode_check
async def post_file_visible(_: Request, body: schema.MapFileVisibleRequest):
    try:
        found = lib.set_pmtiles_file_visible(body.map_path, body.visible)
    except ValueError as e:
        return response.json({'error': str(e)}, HTTPStatus.BAD_REQUEST)

    if found:
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
        with request.ctx.db.write() as session:
            await lib.subscribe(session, body.name, body.region)
    except ValueError as e:
        return response.json({'error': str(e)}, HTTPStatus.BAD_REQUEST)

    Events.send_created(f'Map subscription created for {body.name}')
    return response.empty(HTTPStatus.CREATED)


@map_bp.delete('/subscribe/<region:str>')
@openapi.description('Unsubscribe from a map region')
@wrol_mode_check
async def delete_subscription(request: Request, region: str):
    try:
        with request.ctx.db.write() as session:
            await lib.unsubscribe(session, region)
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
    try:
        pin = get_map_pins_config().add_pin(body.lat, body.lon, body.label, body.color, body.kind,
                                            body.weapon, body.yield_kt, body.fission_fraction)
    except ValueError as e:
        return response.json({'error': str(e)}, HTTPStatus.BAD_REQUEST)
    return json_response(dict(pin=pin), HTTPStatus.CREATED)


@map_bp.put('/pins/targets/weapon')
@openapi.description('Give every target one weapon')
@validate(schema.MapTargetsWeaponRequest)
async def put_targets_weapon(_: Request, body: schema.MapTargetsWeaponRequest):
    try:
        count = get_map_pins_config().set_targets_weapon(body.weapon, body.yield_kt, body.fission_fraction)
    except ValueError as e:
        return response.json({'error': str(e)}, HTTPStatus.BAD_REQUEST)
    return json_response(dict(targets=count), HTTPStatus.OK)


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
    try:
        updated = get_map_pins_config().update_pin(pin_id, body.label, body.color, body.weapon, body.yield_kt,
                                                   body.fission_fraction)
    except ValueError as e:
        return response.json({'error': str(e)}, HTTPStatus.BAD_REQUEST)
    if updated:
        return response.empty(HTTPStatus.NO_CONTENT)
    return response.json({'error': 'Pin not found'}, HTTPStatus.NOT_FOUND)


@map_bp.get('/search')
@openapi.description('Search for places in map search indexes')
async def search_places(request: Request):
    q = request.args.get('q', '')
    if not q or len(q.strip()) < 1:
        return json_response({'error': 'Query parameter "q" is required'}, HTTPStatus.BAD_REQUEST)

    try:
        limit = int(request.args.get('limit', 12))
        offset = int(request.args.get('offset', 0))
        lat = float(request.args.get('lat')) if request.args.get('lat') is not None else None
        lon = float(request.args.get('lon')) if request.args.get('lon') is not None else None
    except (ValueError, TypeError):
        return json_response({'error': 'Invalid query parameters'}, HTTPStatus.BAD_REQUEST)

    data = search.search_places(q.strip(), limit=limit, offset=offset, lat=lat, lon=lon)
    return json_response(data, HTTPStatus.OK)


@map_bp.get('/search/estimate')
@openapi.description('Get estimated count of map search results')
async def get_search_estimate(request: Request):
    q = request.args.get('q', '')
    if not q or len(q.strip()) < 1:
        return json_response({'map_places': 0}, HTTPStatus.OK)
    count = search.search_places_count(q.strip())
    return json_response({'map_places': count}, HTTPStatus.OK)


@map_bp.get('/search/status')
@openapi.description('Get status of map search indexes')
async def get_search_status(_: Request):
    status = search.get_search_status()
    return json_response(status, HTTPStatus.OK)


@map_bp.post('/search/rebuild')
@openapi.description('Rebuild all map search indexes')
@wrol_mode_check
async def rebuild_search_indexes(_: Request):
    started = search.rebuild_all_search_indexes()
    if started:
        return json_response({'message': 'Search index rebuild started'}, HTTPStatus.ACCEPTED)
    return json_response({'error': 'No PMTiles files found'}, HTTPStatus.NOT_FOUND)


@map_bp.post('/search/rebuild/<filename:path>')
@openapi.description('Rebuild search index for a single PMTiles file')
@wrol_mode_check
async def rebuild_single_search_index(_: Request, filename: str):
    try:
        started = search.rebuild_search_index(filename)
    except ValueError as e:
        return response.json({'error': str(e)}, HTTPStatus.BAD_REQUEST)

    if started:
        return json_response({'message': f'Search index rebuild started for {filename}'}, HTTPStatus.ACCEPTED)
    return json_response({'error': 'File not found'}, HTTPStatus.NOT_FOUND)


@map_bp.get('/quad')
@openapi.description('The name of the USGS quadrangle of an area of the map')
async def get_quad(request: Request):
    """What the USGS calls the quadrangle between `west`, `south`, `east` and `north` (degrees): `quad` is its
    `name`, its `state`, and whether it is `exact`ly that area (and not a larger quadrangle which has the middle
    of it); or null where there is no name, which is most of the world."""
    try:
        west, south, east, north = (float(request.args.get(i)) for i in ('west', 'south', 'east', 'north'))
    except (TypeError, ValueError):
        return response.json({'error': 'The edges of the area are four numbers'}, HTTPStatus.BAD_REQUEST)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        # Not so of a number which is not one, either.
        return response.json({'error': 'The edges are not those of an area of the map'}, HTTPStatus.BAD_REQUEST)
    # The index is read from its file the first time, which is not for the event loop.
    name = await asyncio.to_thread(quads.quad_name, west, south, east, north)
    return json_response({'quad': name.__json__() if name else None})


# How much may be written on the sheet of an exported map.
SHEET_TEXT_LENGTH = 300
SHEET_CREDITS = 40


def _export_text(value) -> str:
    """What was sent as text of an exported map (its title, the name of a layer), as it can be written in a PDF:
    no longer than a line of a sheet, and with nothing in it which is not a character."""
    text = str(value or '').replace('\x00', '')
    return text.encode('utf-8', 'replace').decode('utf-8')[:SHEET_TEXT_LENGTH]


def _sheet_contours(contours) -> dict:
    """How far apart the contour lines of a map are, as the browser says it, for `export.Sheet`.  A map with no
    contour lines says nothing; what is said is written on the sheet only when it is an interval (see
    `modules.map.sheet`)."""
    if not isinstance(contours, dict):
        return {}
    interval = contours.get('interval')
    if isinstance(interval, bool) or not isinstance(interval, (int, float)):
        return {}
    return dict(contour_interval=float(interval), contour_unit=str(contours.get('unit') or '')[:SHEET_TEXT_LENGTH])


def _export_error(e: Exception):
    """The response for an export which could not go on."""
    if isinstance(e, export_job.ExportNotFound):
        return response.json({'error': str(e)}, HTTPStatus.NOT_FOUND)
    if isinstance(e, export_job.ExportNotReady):
        return response.json({'error': str(e)}, HTTPStatus.CONFLICT)
    if isinstance(e, export_job.ExportStorageError):
        return response.json({'error': str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)
    return response.json({'error': str(e)}, HTTPStatus.BAD_REQUEST)


EXPORT_ERRORS = (export.InvalidExport, export_job.ExportNotFound, export_job.ExportNotReady,
                 export_job.ExportStorageError)


@map_bp.post('/export')
@openapi.description('Begin the export of a map as a PDF')
async def post_export(request: Request):
    """The browser draws the map, one image for each layer; the API puts them in a PDF, each in a layer of its own.
    That takes a minute or two on a Raspberry Pi, so it is a Job:

    1. This request describes the map, and is answered with an `export_id`.
    2. `POST /api/map/export/<export_id>/layer/<index>` sends the image of each layer.
    3. `POST /api/map/export/<export_id>/start` is answered with a `job_id`, to watch at `/api/jobs/<job_id>`.
    4. `GET /api/map/export/<export_id>/pdf` is the PDF, once the Job is complete.

    `DELETE /api/map/export/<export_id>` stops an export at any of those steps, and removes what was sent.

    The JSON body: `width` and `height` in pixels, `dpi`, `title`, `layers`: the name of each image from the bottom
    up (images of one name are one layer of the PDF), `bounds`: the west, south, east and north edges of the images in degrees, with which the PDF says where it
    is, and `sheet`: with which the map is put on a sheet with a margin and a grid; `name`, `credits` and `date`
    are written on it, `contours` (`{"interval": 40, "unit": "feet"}`, or "meters") when the map has contour
    lines, and `legend`: the lines of the map as they are drawn (see `modules.map.sheet.Sheet`)."""
    try:
        meta = request.json
        width, height, dpi = int(meta['width']), int(meta['height']), float(meta['dpi'])
        names = [_export_text(i) for i in meta['layers']]
        title = _export_text(meta.get('title')) or None
        bounds = meta.get('bounds')
        sheet = meta.get('sheet')
        if sheet is not None:
            sheet = export.Sheet(
                name=_export_text(sheet.get('name')) or None,
                credits=[_export_text(i) for i in (sheet.get('credits') or [])[:SHEET_CREDITS]],
                date=_export_text(sheet.get('date')) or None,
                **_sheet_contours(sheet.get('contours')),
                legend=legend_as_sent(sheet.get('legend')),
            )
    except Exception:  # noqa Whatever is made of a body which is not the description of a map.
        return response.json({'error': 'The description of the map is not valid'}, HTTPStatus.BAD_REQUEST)

    try:
        # Old exports are removed from the disk here, which is not for the event loop.
        export_id = await asyncio.to_thread(export_job.create_export, names, width, height, dpi, title, bounds, sheet)
    except EXPORT_ERRORS as e:
        return _export_error(e)
    return json_response({'export_id': export_id}, HTTPStatus.CREATED)


@map_bp.post('/export/<export_id:str>/layer/<index:int>')
@openapi.description('Send the image (PNG or JPEG) of one layer of a map which is being exported')
async def post_export_layer(request: Request, export_id: str, index: int):
    try:
        await asyncio.to_thread(export_job.save_layer, export_id, index, request.body)
    except EXPORT_ERRORS as e:
        return _export_error(e)
    return response.empty()


@map_bp.post('/export/<export_id:str>/start')
@openapi.description('Queue the Job which makes the PDF of a map, all of whose layers have been sent')
async def post_export_start(_: Request, export_id: str):
    try:
        job_id = await asyncio.to_thread(export_job.start_export, export_id)
    except EXPORT_ERRORS as e:
        return _export_error(e)
    return json_response({'job_id': job_id}, HTTPStatus.ACCEPTED)


@map_bp.delete('/export/<export_id:str>')
@openapi.description('Stop the export of a map: cancel its Job, if it has one, and remove what was sent')
async def delete_export(_: Request, export_id: str):
    try:
        await asyncio.to_thread(export_job.remove_export, export_id)
    except EXPORT_ERRORS as e:
        return _export_error(e)
    return response.empty()


@map_bp.get('/export/<export_id:str>/pdf')
@openapi.description('The PDF of an exported map, once the Job which makes it is complete')
async def get_export_pdf(_: Request, export_id: str):
    try:
        pdf = await asyncio.to_thread(export_job.get_export_pdf, export_id)
    except EXPORT_ERRORS as e:
        return _export_error(e)
    return await response.file(pdf, mime_type='application/pdf', filename='map.pdf')


@map_bp.get('/fallout/winds/latest')
@openapi.description('The field of forecast winds aloft fetched most recently')
def get_latest_fallout_winds(_: Request):
    return json_response(dict(winds=winds.latest_field()), HTTPStatus.OK)


@map_bp.post('/fallout/winds')
@openapi.description('Fetch the field of forecast winds aloft over places (the targets)')
@validate(schema.MapFalloutWindsRequest)
async def post_fallout_winds(_: Request, body: schema.MapFalloutWindsRequest):
    if not flags.have_internet.is_set():
        return response.json({'error': 'WROLPi has no Internet, so it cannot fetch a forecast'},
                             HTTPStatus.SERVICE_UNAVAILABLE)
    try:
        places = [(float(lat), float(lon)) for lat, lon in body.places]
    except (TypeError, ValueError):
        return response.json({'error': 'places are [lat, lon]'}, HTTPStatus.BAD_REQUEST)
    try:
        field = await winds.fetch_wind_field(places)
    except winds.WindsError as e:
        return response.json({'error': str(e)}, HTTPStatus.BAD_GATEWAY)
    return json_response(dict(winds=field), HTTPStatus.OK)
