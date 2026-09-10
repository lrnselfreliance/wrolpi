"""The /api/ai blueprint — read-only, LLM-shaped endpoints.

This blueprint IS the AI tool catalog: the agent loop generates its tool definitions from these
endpoints' OpenAPI operations, and the external MCP server proxies them.  Every endpoint is
read-only; descriptions are written for the model, not for humans.
"""
import asyncio
import mimetypes
import pathlib
from http import HTTPStatus
from typing import Optional

from sanic import Blueprint, Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from modules.archive import lib as archive_lib
from modules.archive.lib import search_domains_by_name
from modules.docs.lib import search_authors_by_name, search_subjects_by_name
from modules.map import lib as map_lib
from modules.map import search as map_search
from modules.map.pins import get_map_pins_config
from modules.videos.channel.lib import search_channels_by_name
from modules.videos.models import Video
from modules.docs.lib import _doc_response, _get_doc, _search_docs
from modules.inventory.common import get_inventory_configs
from modules.inventory.errors import UnknownInventory
from modules.videos.video import lib as videos_lib
from modules.zim import lib as zim_lib
from wrolpi import flags, tags
from wrolpi.api_utils import json_response
from wrolpi.collections.lib import search_collections
from wrolpi.common import api_param_limiter, get_media_directory, get_relative_to_media_directory, logger, \
    wrol_mode_enabled
from wrolpi.downloader import download_manager
from wrolpi.errors import InvalidFile, SearchEmpty, UnknownFile, ValidationError
from wrolpi.files.lib import search_files, HIDDEN_DIRECTORIES, HIDDEN_FILES
from wrolpi.files.models import FileGroup
from wrolpi.vars import DOCKERIZED, IS_RPI4
from wrolpi.version import __version__
from wrolpi.schema import JSONErrorResponse
from . import catalog, help_docs, lib, schema
from .config import get_ai_config
from .controller_client import controller_get
from .errors import ControllerUnavailable

ai_bp = Blueprint('AI', url_prefix='/api/ai')

logger = logger.getChild(__name__)

ai_limiter = api_param_limiter(25, default=5)

# Refuse to serve files this large through the text reader; real content is paged anyway.
MAX_TEXT_FILE_SIZE = 10 * 1024 * 1024
# Directory listings are paged by entry count so one big channel can't fill the model's context.
LIST_PAGE_SIZE = 100


def _offset(request: Request) -> int:
    try:
        return max(int(request.args.get('offset', 0)), 0)
    except ValueError:
        return 0


@ai_bp.get('/zims')
@openapi.definition(
    summary='List Zim encyclopedias',
    description='List the Zim encyclopedias in the library (Wikipedia, Wiktionary, etc.). Returns the zim_id'
                ' needed to search a specific Zim or read one of its entries.',
)
@openapi.operation('list_zims')
async def list_zims(request: Request):
    zims = zim_lib.get_zims(request.ctx.session)
    results = []
    for zim in zims:
        metadata = lib.zim_metadata_dict(zim.zim_metadata)
        results.append({k: v for k, v in dict(
            id=zim.id,
            title=metadata.get('title'),
            creator=metadata.get('creator'),
            description=metadata.get('description'),
            size=zim.file_group.size if zim.file_group else None,
            auto_search=zim.auto_search,
        ).items() if v is not None})
    return json_response(dict(results=results, total=len(results)))


@ai_bp.post('/zims/search')
@openapi.definition(
    summary='Search Zim encyclopedias',
    description='Search the Zim encyclopedias (Wikipedia, etc.) enabled for search; pass zim_id to search one.'
                ' Read a result in full with get_zim_entry (zim_id and path).',
    body=schema.AIZimSearchRequest,
)
@openapi.operation('search_zims')
@openapi.response(HTTPStatus.OK, schema.AISearchResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
@validate(schema.AIZimSearchRequest)
async def search_zims(request: Request, body: schema.AIZimSearchRequest):
    if not body.search_str:
        raise SearchEmpty()
    limit = ai_limiter(body.limit)
    offset = body.offset or 0
    if body.zim_id:
        result = zim_lib.headline_zim(request.ctx.session, body.search_str, body.zim_id, offset=offset, limit=limit)
        for entry in result.get('search') or []:
            entry['zim_id'] = body.zim_id
        zim_results = [result]
    else:
        zim_results = zim_lib.search_all_zims(request.ctx.session, body.search_str, offset=offset, limit=limit)
    return json_response(lib.format_zim_search(zim_results))


@ai_bp.get('/zims/<zim_id:int>/entry')
@openapi.definition(
    summary='Read a Zim entry',
    description='Read one Zim article as plain text by zim_id and the path from search_zims. Paged: request'
                ' again with offset=next_offset.',
)
@openapi.operation('get_zim_entry')
@openapi.parameter('path', str, 'query')
@openapi.parameter('offset', int, 'query')
@openapi.response(HTTPStatus.OK, schema.AIPagedTextResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_zim_entry(request: Request, zim_id: int):
    path = request.args.get('path')
    if not path:
        raise InvalidFile('path query parameter is required')
    entry = zim_lib.get_entry(path, zim_id)
    html = bytes(entry.get_item().content).decode('UTF-8', errors='replace')
    result = lib.paginate_text(lib.html_to_text(html), _offset(request))
    result['link'] = lib.zim_entry_link(zim_id, path)
    return json_response(result)


@ai_bp.get('/collections')
@openapi.definition(
    summary='List collections',
    description='List collections in the library, paged. Filter with kind: "channel" (video channels),'
                ' "domain" (archived websites), or "playlist"; search_str matches names. Use a channel\'s'
                ' name or id, or a domain\'s name, as the channel or domain filter of search_files.',
)
@openapi.operation('list_collections')
@openapi.parameter('kind', str, 'query')
@openapi.parameter('search_str', str, 'query')
@openapi.parameter('limit', int, 'query')
@openapi.parameter('offset', int, 'query')
async def list_collections(request: Request):
    kind = request.args.get('kind')
    search_str = request.args.get('search_str') or None
    try:
        limit = ai_limiter(int(request.args.get('limit', 0)) or None)
    except ValueError:
        raise ValidationError('limit must be an integer')
    offset = _offset(request)
    collections = search_collections(request.ctx.session, kind=kind, search_str=search_str)
    results = []
    for collection in collections[offset:offset + limit]:
        # Channels have a browsable page; a real link stops the model inventing one.
        link = f"/videos/channel/{collection['id']}/video" if collection.get('kind') == 'channel' else None
        results.append({k: v for k, v in dict(
            id=collection.get('id'),
            name=collection.get('name'),
            kind=collection.get('kind'),
            directory=collection.get('directory'),
            link=link,
        ).items() if v is not None})
    next_offset = offset + limit if offset + limit < len(collections) else None
    return json_response(dict(results=results, total=len(collections), next_offset=next_offset))


def _lean_inventories() -> list:
    return [{k: v for k, v in dict(
        slug=i.get('slug'),
        name=i.get('name'),
        type=i.get('type'),
        item_count=len(i.get('items') or []),
    ).items() if v is not None} for i in get_inventory_configs().all_inventories()]


def _inventory_by_slug(slug: str) -> dict:
    inventory = get_inventory_configs().get_inventory(slug)
    if inventory is None:
        raise UnknownInventory(f'No inventory: {slug}')
    return inventory


@ai_bp.get('/inventories')
@openapi.definition(
    summary='Get inventories',
    description='Without slug: list the inventories (food storage, emergency supplies, etc.) with item counts.'
                ' With slug: that inventory in full, every item and field.',
)
@openapi.operation('get_inventory')
@openapi.parameter('slug', str, 'query')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_inventory(request: Request):
    if slug := request.args.get('slug'):
        return json_response(dict(inventory=_inventory_by_slug(slug)))
    results = _lean_inventories()
    return json_response(dict(results=results, total=len(results)))


# ---------------------------------------------------------------------------
# Help endpoints (Help mode).  Help markdown is searched in-process; see help_docs.py.
# ---------------------------------------------------------------------------

@ai_bp.post('/help/search')
@openapi.definition(
    summary='Search the WROLPi help documentation',
    description='Search the WROLPi help documentation for how to use and repair WROLPi. Returns matching'
                ' help pages with a snippet; read a full page by passing its slug to get_help_doc. Links are pages on the'
                ' WROLPi help site.',
    body=schema.AIHelpSearchRequest,
)
@openapi.operation('search_help')
@openapi.response(HTTPStatus.OK, schema.AISearchResponse)
@validate(schema.AIHelpSearchRequest)
async def search_help(_: Request, body: schema.AIHelpSearchRequest):
    if not body.search_str:
        raise SearchEmpty()
    if not help_docs.get_help_docs_directory():
        return json_response(dict(results=[], total=0, message='Help documentation is not installed.'))
    results, total = help_docs.search_help(body.search_str, ai_limiter(body.limit))
    return json_response(dict(results=results, total=total))


@ai_bp.get('/help/<slug:path>')
@openapi.definition(
    summary='Read a help page',
    description='Read one WROLPi help page as markdown by its doc slug from search_help results. Long'
                ' pages are paged: request again with offset=next_offset to continue reading.',
)
@openapi.operation('get_help_doc')
@openapi.parameter('offset', int, 'query')
@openapi.response(HTTPStatus.OK, schema.AIPagedTextResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_help_doc(request: Request, slug: str):
    doc = help_docs.get_help_doc(slug)
    if not doc:
        raise UnknownFile(f'No such help doc: {slug}')
    result = lib.paginate_text(doc.body, _offset(request))
    result['title'] = doc.title
    result['link'] = help_docs.help_doc_link(doc.slug)
    return json_response(result)


# ---------------------------------------------------------------------------
# System endpoints (System mode).  The Controller is proxied so the model sees one API; every
# proxy degrades gracefully — a Controller outage becomes an entry in `errors`, never a 500.
# ---------------------------------------------------------------------------

# The lean subset of the Controller's cached status that is useful for diagnosis; the full blob
# (processes, iostat, disk bandwidth) is too big for small model contexts.
SYSTEM_STATUS_KEYS = ('cpu', 'memory', 'load', 'drives', 'network', 'uptime', 'hotspot', 'throttle', 'is_rpi')

log_lines_limiter = api_param_limiter(1_000, default=100)


@ai_bp.get('/status')
@openapi.definition(
    summary='Get WROLPi system status',
    description='Get an aggregate of the whole system in one call: WROLPi version, mode flags, download'
                ' summary, CPU/memory/load/disk usage, and the state of every WROLPi service. Start'
                ' troubleshooting here. Any part that could not be gathered is listed in errors.',
)
@openapi.operation('get_system_status')
async def get_system_status(_: Request):
    errors = []
    ret = dict(
        version=__version__.strip(),
        dockerized=DOCKERIZED,
        wrol_mode=wrol_mode_enabled(),
        flags=flags.get_flags(),
        errors=errors,
    )

    try:
        ret['downloads'] = download_manager.get_summary()
    except Exception as e:
        logger.debug('AI status could not get download summary', exc_info=e)
        errors.append('Could not get download summary')

    try:
        status, stats = await controller_get('/api/stats')
        if status == HTTPStatus.OK:
            ret['system'] = {k: v for k, v in stats.items() if k in SYSTEM_STATUS_KEYS}
        else:
            errors.append(f'Controller stats returned HTTP {status}')
    except Exception as e:
        logger.debug('AI status could not reach Controller stats', exc_info=e)
        errors.append('Could not reach the Controller for system stats')

    try:
        ret['services'] = await _lean_services()
    except Exception as e:
        logger.debug('AI status could not get services', exc_info=e)
        errors.append('Could not get service statuses')

    return json_response(ret)


async def _lean_services() -> list:
    status, services = await controller_get('/api/services')
    if status != HTTPStatus.OK or not isinstance(services, list):
        raise ControllerUnavailable(f'Controller services returned HTTP {status}')
    return [{k: v for k, v in dict(
        name=i.get('name'),
        status=i.get('status'),
        enabled=i.get('enabled'),
        port=i.get('port'),
        description=i.get('description') or None,
    ).items() if v is not None} for i in services]


@ai_bp.get('/services')
@openapi.definition(
    summary='List WROLPi services',
    description='List every WROLPi service with its state (running, stopped, failed) and port. Use the'
                ' name with get_service_logs to read a failing service\'s logs.',
)
@openapi.operation('list_services')
@openapi.response(HTTPStatus.BAD_GATEWAY, JSONErrorResponse)
async def ai_list_services(_: Request):
    services = await _lean_services()
    return json_response(dict(results=services, total=len(services)))


@ai_bp.get('/services/<name:str>/logs')
@openapi.definition(
    summary='Read service logs',
    description='Read the most recent log lines of one WROLPi service by its name from list_services.'
                ' Pass lines to read more history (at most 1000).',
)
@openapi.operation('get_service_logs')
@openapi.parameter('lines', int, 'query')
@openapi.parameter('since', str, 'query')
@openapi.response(HTTPStatus.BAD_GATEWAY, JSONErrorResponse)
async def ai_get_service_logs(request: Request, name: str):
    try:
        lines = log_lines_limiter(int(request.args.get('lines', 100)))
    except ValueError:
        lines = 100
    status, body = await controller_get(f'/api/services/{name}/logs',
                                        params=dict(lines=max(lines, 1), since=request.args.get('since')))
    if status != HTTPStatus.OK:
        raise ControllerUnavailable(f'Controller logs returned HTTP {status}: {body.get("detail")}')
    return json_response(dict(service=body.get('service', name), lines=body.get('lines'), logs=body.get('logs', '')))


@ai_bp.get('/disks')
@openapi.definition(
    summary='Get disks and drive health',
    description='List the disks and partitions (size, filesystem, where mounted) and SMART drive-health'
                ' status. Use this to diagnose full or failing drives. Parts that could not be gathered'
                ' are listed in errors.',
)
@openapi.operation('list_disks')
async def ai_list_disks(_: Request):
    errors = []
    ret = dict(errors=errors)

    try:
        status, disks = await controller_get('/api/disks')
        if status == HTTPStatus.OK:
            ret['disks'] = disks
        else:
            errors.append(f'Controller disks returned HTTP {status}: {disks.get("detail")}')
    except Exception as e:
        logger.debug('AI disks could not reach Controller', exc_info=e)
        errors.append('Could not reach the Controller for disks')

    try:
        status, smart = await controller_get('/api/disks/smart')
        if status == HTTPStatus.OK:
            ret['smart'] = smart
        else:
            errors.append(f'Controller SMART returned HTTP {status}: {smart.get("detail")}')
    except Exception as e:
        logger.debug('AI disks could not reach Controller SMART', exc_info=e)
        errors.append('Could not reach the Controller for SMART status')

    return json_response(ret)


# Errors on downloads can be long tracebacks; the model only needs the gist.
DOWNLOAD_ERROR_LENGTH = 300
MAP_LINK_ZOOM = 12


def _map_link(lat, lon) -> str:
    return f'/map?lat={lat}&lon={lon}&z={MAP_LINK_ZOOM}'


@ai_bp.get('/tags')
@openapi.definition(
    summary='List tags',
    description='List every tag in the library with how many files, Zim entries, channels, and domains carry'
                ' it, plus the most recently used tag names. Use a tag name in the tag_names filter of the'
                ' search tools. Users tag things they care about, so tags are a good map of their interests.',
)
@openapi.operation('list_tags')
async def list_tags(_: Request):
    results = [dict(
        name=i['name'],
        file_groups=i['file_group_count'],
        zim_entries=i['zim_entry_count'],
        channels=i['channel_count'],
        domains=i['domain_count'],
    ) for i in tags.get_tags()]
    return json_response(dict(results=results, recent=tags.get_recent_tags(), total=len(results)))


def _format_download(download: dict) -> dict:
    error = download.get('error')
    if error and len(error) > DOWNLOAD_ERROR_LENGTH:
        # Errors are usually tracebacks; the exception message at the end is the useful part.
        error = '…' + error[-DOWNLOAD_ERROR_LENGTH:]
    destination = download.get('destination')
    return {k: v for k, v in dict(
        id=download.get('id'),
        url=download.get('url'),
        status=download.get('status'),
        downloader=download.get('downloader'),
        sub_downloader=download.get('sub_downloader'),
        frequency=download.get('frequency'),
        destination=str(get_relative_to_media_directory(destination)) if destination else None,
        collection_id=download.get('collection_id'),
        tag_names=download.get('tag_names') or None,
        next_download=download.get('next_download'),
        last_successful_download=download.get('last_successful_download'),
        error=error,
    ).items() if v is not None}


@ai_bp.get('/downloads')
@openapi.definition(
    summary='List downloads',
    description='Read the download queue: a summary (pending count, whether downloading is disabled or'
                ' stopped, daily limit), the recurring downloads (channels, feeds; frequency is in seconds),'
                ' and the newest one-time downloads. Filter with status: new, pending, failed, deferred, or'
                ' complete. Use this when the user asks what is downloading, why a download failed, or what'
                ' is scheduled. You cannot start, stop, or retry downloads.',
)
@openapi.operation('list_downloads')
@openapi.parameter('status', str, 'query')
@openapi.parameter('limit', int, 'query')
async def list_downloads(request: Request):
    status = request.args.get('status')
    try:
        limit = ai_limiter(int(request.args.get('limit', 0)) or None)
    except ValueError:
        raise ValidationError('limit must be an integer')
    summary = download_manager.get_summary()
    data = download_manager.get_fe_downloads()

    def select(downloads: list) -> list:
        if status:
            downloads = [i for i in downloads if i.get('status') == status]
        return [_format_download(i) for i in downloads[:limit]]

    return json_response(dict(
        summary=summary,
        recurring=select(data['recurring_downloads']),
        once=select(data['once_downloads']),
        pending_once=data.get('pending_once_downloads', 0),
    ))


@ai_bp.get('/map')
@openapi.definition(
    summary='Get map overview',
    description='What maps this WROLPi has: the downloaded map files (regions) and whether each has a place'
                ' search index, the map regions subscribed for updates, and the user\'s saved pins with a'
                ' link to each. Use search_places to look up a town or landmark.',
)
@openapi.operation('get_map_overview')
async def get_map_overview(request: Request):
    files = [dict(name=i['name'], path=i['path'], size=i['size'], has_search_index=i['has_search_index'])
             for i in map_lib.get_pmtiles_files()]
    pins = [dict(id=i.get('id'), label=i.get('label'), lat=i.get('lat'), lon=i.get('lon'),
                 link=_map_link(i.get('lat'), i.get('lon')))
            for i in get_map_pins_config().pins]
    return json_response(dict(
        files=files,
        subscriptions=map_lib.get_map_subscriptions(request.ctx.session),
        pins=pins,
        search_indexes=map_search.get_search_status(),
    ))


@ai_bp.get('/map/search')
@openapi.definition(
    summary='Search places on the map',
    description='Find towns, cities, and landmarks by name in the downloaded maps. Each result has coordinates'
                ' and a map link. Pass lat and lon to rank nearest first.',
)
@openapi.operation('search_places')
@openapi.parameter('q', str, 'query')
@openapi.parameter('limit', int, 'query')
@openapi.parameter('offset', int, 'query')
@openapi.parameter('lat', float, 'query')
@openapi.parameter('lon', float, 'query')
async def search_places(request: Request):
    q = (request.args.get('q') or '').strip()
    if not q:
        raise ValidationError('q query parameter is required')
    try:
        limit = ai_limiter(int(request.args.get('limit', 0)) or None)
        lat = float(request.args.get('lat')) if request.args.get('lat') is not None else None
        lon = float(request.args.get('lon')) if request.args.get('lon') is not None else None
    except ValueError:
        raise ValidationError('limit, lat, and lon must be numbers')
    data = await asyncio.to_thread(map_search.search_places, q, limit=limit, offset=_offset(request),
                                   lat=lat, lon=lon)
    results = [{k: v for k, v in dict(
        name=i.get('name'),
        kind=i.get('kind_detail') or i.get('kind'),
        region=i.get('region'),
        population=i.get('population'),
        lat=i.get('lat'),
        lon=i.get('lon'),
        link=_map_link(i.get('lat'), i.get('lon')),
    ).items() if v is not None} for i in data.get('results') or []]
    return json_response(dict(results=results, total=data.get('total', len(results))))


# ---------------------------------------------------------------------------
# Consolidated, kind-generic endpoints.  Small models carry every tool definition on every request,
# so one search / one detail / one reader replaces the per-kind trio.
# ---------------------------------------------------------------------------

FILE_KINDS = ('video', 'archive', 'doc')
# Name matches offered alongside search results so the model can narrow without another tool.
MATCHES_PER_GROUP = 3


def _archive_detail(archive) -> dict:
    result = lib.format_file_group(archive.file_group.__json__(),
                                   description_length=lib.DETAIL_DESCRIPTION_LENGTH, include_url=True, detail=True)
    history = []
    for snapshot in archive.history[:10]:
        fg = snapshot.file_group.__json__()
        history.append({k: v for k, v in dict(
            id=fg.get('id'),
            title=fg.get('title') or fg.get('name'),
            published=lib.format_date(fg.get('published_datetime')),
            link=lib.wrolpi_link(fg),
        ).items() if v is not None})
    if history:
        result['history'] = history
    return result


def _video_detail(video: Video) -> dict:
    fg = video.__json__()
    try:
        fg['video']['description'] = video.get_description()
    except Exception as e:
        logger.debug(f'Could not read description of {video}', exc_info=e)
    result = lib.format_file_group(fg, description_length=lib.DETAIL_DESCRIPTION_LENGTH, detail=True)
    result['has_captions'] = bool(video.caption_paths)
    if video.have_comments:
        result['has_comments'] = True
    return result


def _doc_detail(session, file_group_id: int) -> dict:
    response = _doc_response(_get_doc(session, file_group_id))
    file_group = response['file_group']
    file_group['doc'] = response['doc']
    return lib.format_file_group(file_group, description_length=lib.DETAIL_DESCRIPTION_LENGTH, detail=True)


async def _resolve_channel_id(session, channel: str) -> Optional[int]:
    """A channel given as a numeric id or a (partial) name; None when nothing matches."""
    channel = (channel or '').strip()
    if not channel:
        return None
    if channel.isdigit():
        return int(channel)
    matches = await search_channels_by_name(session, channel, limit=1, order_by_video_count=True)
    return matches[0].id if matches else None


@ai_bp.post('/files/search')
@openapi.definition(
    summary='Search the library',
    description='Search videos, archived web pages, and documents by title and content; omit search_str to'
                ' browse the newest. kind: video, archive, or doc. channel (name or id) is for videos, domain for'
                ' archives, author/subject for docs. Each result has an id for get_file/read_content and a link.'
                ' matches names channels/domains/authors that fit the term: narrow with one when total is large.',
    body=schema.AIFileSearchRequest,
)
@openapi.operation('search_files')
@openapi.response(HTTPStatus.OK, schema.AISearchResponse)
@validate(schema.AIFileSearchRequest)
async def search_files_endpoint(request: Request, body: schema.AIFileSearchRequest):
    session = request.ctx.session
    kind = (body.kind or '').strip().lower() or None
    if kind and kind not in FILE_KINDS:
        raise ValidationError(f'kind must be one of {", ".join(FILE_KINDS)}')
    # A kind-specific filter implies the kind.
    if not kind:
        if body.channel:
            kind = 'video'
        elif body.domain:
            kind = 'archive'
        elif body.author or body.subject:
            kind = 'doc'

    limit = ai_limiter(body.limit)
    offset = body.offset or 0
    searched = bool(body.search_str)
    narrowed = False

    if kind == 'video':
        channel_id = None
        if body.channel:
            channel_id = await _resolve_channel_id(session, body.channel)
            if channel_id is None:
                result = lib.format_file_groups([], 0, searched=True)
                result['hint'] = (f'No channel matches "{body.channel}". Use the exact channel name from the'
                                  ' library list, or search without channel.')
                return json_response(result)
            narrowed = True
        file_groups, total = videos_lib.search_videos(
            search_str=body.search_str, offset=offset, limit=limit, channel_id=channel_id,
            tag_names=body.tag_names, headline=True)
    elif kind == 'archive':
        narrowed = bool(body.domain)
        file_groups, total = archive_lib.search_archives(
            body.search_str, body.domain, limit, offset, None, body.tag_names, headline=True)
    elif kind == 'doc':
        narrowed = bool(body.author or body.subject)
        file_groups, total = _search_docs(
            search_str=body.search_str, author=body.author, subject=body.subject, limit=limit, offset=offset,
            order_by='rank' if body.search_str else 'published_datetime', tag_names=body.tag_names)
    else:
        file_groups, total = search_files(body.search_str, limit, offset, tag_names=body.tag_names, headline=True)

    result = lib.format_file_groups(file_groups, total, searched=searched)

    if searched and not narrowed:
        matches = dict()
        channels = await search_channels_by_name(session, body.search_str, limit=MATCHES_PER_GROUP,
                                                 order_by_video_count=True)
        if channels and kind in (None, 'video'):
            matches['channels'] = [dict(id=i.id, name=i.name) for i in channels]
        domains = await search_domains_by_name(session, body.search_str, limit=MATCHES_PER_GROUP)
        if domains and kind in (None, 'archive'):
            matches['domains'] = [dict(name=i['domain']) for i in domains]
        if kind in (None, 'doc'):
            authors = await search_authors_by_name(session, body.search_str, limit=MATCHES_PER_GROUP)
            subjects = await search_subjects_by_name(session, body.search_str, limit=MATCHES_PER_GROUP)
            if authors:
                matches['authors'] = [dict(name=i['name']) for i in authors]
            if subjects:
                matches['subjects'] = [dict(name=i['name']) for i in subjects]
        if matches:
            result['matches'] = matches

    return json_response(result)


@ai_bp.get('/files/<file_group_id:int>')
@openapi.definition(
    summary='Get one file',
    description='Details of one item by its id, any kind: title, link, date, channel/author, tags, size, full'
                ' description; videos say whether captions/comments exist; archives include earlier snapshots.',
)
@openapi.operation('get_file')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_file(request: Request, file_group_id: int):
    session = request.ctx.session
    file_group = FileGroup.find_by_id(session, file_group_id)
    if file_group.model == 'video':
        return json_response(_video_detail(Video.find_by_file_group_id(session, file_group_id)))
    if file_group.model == 'archive':
        archive = archive_lib.get_archive_by_file_group_id(session, file_group_id, skip_viewed=True)
        return json_response(_archive_detail(archive))
    if file_group.model == 'doc':
        return json_response(_doc_detail(session, file_group_id))
    return json_response(lib.format_file_group(file_group.__json__(),
                                               description_length=lib.DETAIL_DESCRIPTION_LENGTH, detail=True))


CONTENT_PARTS = ('text', 'comments')


@ai_bp.get('/files/<file_group_id:int>/content')
@openapi.definition(
    summary='Read a file\'s content',
    description='Read an item by its id: part=text is a video\'s captions or an archived page\'s text;'
                ' part=comments is a video\'s comments. Paged: request again with offset=next_offset.',
)
@openapi.operation('read_content')
@openapi.parameter('part', str, 'query')
@openapi.parameter('offset', int, 'query')
@openapi.response(HTTPStatus.OK, schema.AIPagedTextResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def read_content(request: Request, file_group_id: int):
    part = (request.args.get('part') or 'text').strip().lower()
    if part not in CONTENT_PARTS:
        raise ValidationError(f'part must be one of {", ".join(CONTENT_PARTS)}')
    session = request.ctx.session
    file_group = FileGroup.find_by_id(session, file_group_id)
    kind = file_group.model or 'file'

    text = None
    if kind == 'video':
        video = Video.find_by_file_group_id(session, file_group_id)
        if part == 'text':
            text = lib.format_caption_chunks(video.get_caption_chunks())
        else:
            lines = []
            for comment in video.get_comments() or []:
                author = comment.get('author') or 'unknown'
                if body := (comment.get('text') or '').strip():
                    lines.append(f'{author}: {body}')
            text = '\n'.join(lines)
    elif kind == 'archive' and part == 'text':
        archive = archive_lib.get_archive_by_file_group_id(session, file_group_id, skip_viewed=True)
        text = lib.read_archive_text(archive)

    if text is None:
        raise UnknownFile(f'This is a {kind}; it has no {part} to read')
    return json_response(lib.paginate_text(text, _offset(request)))


# ---------------------------------------------------------------------------
# Manage endpoints — for the AI page's Manage tab, NOT part of the model's tool catalog.
# The agent loop excludes everything under /api/ai/manage/ when building tool definitions.
# ---------------------------------------------------------------------------

@ai_bp.get('/manage/catalog')
@openapi.description('The AI model catalog, download/active state, and the recommended tier for this'
                     ' device.  For the Manage tab, not the model.')
async def manage_catalog(_: Request):
    models, source = await catalog.get_models_catalog()
    models_directory = catalog.get_models_directory()
    downloaded = {i.name for i in models_directory.glob('*.gguf')} if models_directory.is_dir() else set()
    disk_usage = sum(i.stat().st_size for i in models_directory.glob('*')) if models_directory.is_dir() else 0

    config = get_ai_config()
    models = [dict(i, downloaded=i['name'] in downloaded, active=i['name'] == config.active_model)
              for i in models]

    total_ram = catalog.get_total_ram_bytes()
    return json_response(dict(
        models=models,
        catalog_source=source,
        total_ram=total_ram,
        recommended_tier=catalog.recommend_tier(total_ram),
        slow_hardware=IS_RPI4,
        models_directory=str(models_directory),
        disk_usage=disk_usage,
        enabled=config.enabled,
        active_model=config.active_model,
        idle_unload_minutes=config.idle_unload_minutes,
        context_size=config.context_size,
    ))


@ai_bp.post('/manage/settings')
@openapi.definition(
    description='Update the AI settings (ai.yaml).  For the Manage tab, not the model.',
    body=schema.AIManageSettingsRequest,
)
@validate(schema.AIManageSettingsRequest)
async def manage_settings(_: Request, body: schema.AIManageSettingsRequest):
    config = get_ai_config()
    if body.active_model is not None:
        if body.active_model and not (catalog.get_models_directory() / body.active_model).is_file():
            raise ValidationError(f'Model is not downloaded: {body.active_model}')
        config.active_model = body.active_model
        # Each model has its own context default (the 4B runs 16k, the small tier 8k); selecting
        # a model adopts it unless this request also sets context_size explicitly.
        if body.context_size is None and (default := catalog.get_model_default_context(body.active_model)):
            config.context_size = default
    if body.enabled is not None:
        config.enabled = body.enabled
    if body.idle_unload_minutes is not None:
        if body.idle_unload_minutes < 1:
            raise ValidationError('idle_unload_minutes must be at least 1')
        config.idle_unload_minutes = body.idle_unload_minutes
    if body.context_size is not None:
        config.context_size = body.context_size
    return json_response(dict(
        enabled=config.enabled,
        active_model=config.active_model,
        idle_unload_minutes=config.idle_unload_minutes,
        context_size=config.context_size,
    ))


def _resolve_media_path(relative: str | None, verb: str) -> pathlib.Path:
    """Resolve a relative path inside the media directory, refusing escapes and the config directory."""
    media_directory = get_media_directory().resolve()
    path = (media_directory / (relative or '').strip('/')).resolve()
    if path != media_directory and not str(path).startswith(f'{media_directory}/'):
        raise InvalidFile(f'Cannot {verb} outside the media directory')
    # The config directory can contain secrets (Wi-Fi credentials, API keys); never serve it.
    config_directory = media_directory / 'config'
    if path == config_directory or str(path).startswith(f'{config_directory}/'):
        raise InvalidFile(f'Cannot {verb} config files')
    return path


@ai_bp.get('/files/list')
@openapi.definition(
    summary='List a directory',
    description='List one directory of the media directory by relative path (omit for the top level):'
                ' directories first, then files, each with a path for list_files or read_file. Paged by offset.'
                ' For "what is in this folder"; use search_files for content by topic.',
)
@openapi.operation('list_files')
@openapi.parameter('path', str, 'query')
@openapi.parameter('offset', int, 'query')
@openapi.response(HTTPStatus.OK, schema.AIListFilesResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def list_files(request: Request):
    relative = request.args.get('path') or ''
    media_directory = get_media_directory().resolve()
    directory = _resolve_media_path(relative, 'list')
    if not directory.is_dir():
        raise UnknownFile(f'No such directory: {relative}')

    def relative_path(path: pathlib.Path) -> str:
        rel = str(path.relative_to(media_directory))
        return f'{rel}/' if path.is_dir() else rel

    directories, files = [], []
    for child in directory.iterdir():
        if child.is_dir():
            # The config directory is never served (see _resolve_media_path), so don't advertise it.
            if child.name not in HIDDEN_DIRECTORIES and child != media_directory / 'config':
                directories.append(child)
        elif child.name not in HIDDEN_FILES:
            files.append(child)
    directories.sort(key=lambda i: i.name.lower())
    files.sort(key=lambda i: i.name.lower())

    entries = [dict(name=i.name, path=relative_path(i)) for i in directories]
    for file in files:
        try:
            size = file.stat().st_size
        except OSError:
            size = None
        entries.append(dict(name=file.name, path=relative_path(file), size=size,
                            mimetype=mimetypes.guess_type(file.name)[0]))

    offset = _offset(request)
    page = entries[offset:offset + LIST_PAGE_SIZE]
    next_offset = offset + LIST_PAGE_SIZE if offset + LIST_PAGE_SIZE < len(entries) else None
    return json_response(dict(
        path=relative_path(directory) if directory != media_directory else '',
        directories=[i for i in page if 'size' not in i],
        files=[i for i in page if 'size' in i],
        total=len(entries),
        next_offset=next_offset,
    ))


@ai_bp.get('/files/read')
@openapi.definition(
    summary='Read a text file',
    description='Read a plain-text file from the media directory by its relative path (from list_files).'
                ' Text files only. Paged: request again with offset=next_offset.',
)
@openapi.operation('read_file')
@openapi.parameter('path', str, 'query')
@openapi.parameter('offset', int, 'query')
@openapi.response(HTTPStatus.OK, schema.AIPagedTextResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def read_file(request: Request):
    relative = request.args.get('path')
    if not relative:
        raise InvalidFile('path query parameter is required')

    path = _resolve_media_path(relative, 'read')
    if not path.is_file():
        raise UnknownFile(f'No such file: {relative}')
    if path.stat().st_size > MAX_TEXT_FILE_SIZE:
        raise InvalidFile('File is too large to read')

    data = path.read_bytes()
    if b'\x00' in data[:8192]:
        raise InvalidFile('Not a text file')
    return json_response(lib.paginate_text(data.decode('UTF-8', errors='replace'), _offset(request)))
