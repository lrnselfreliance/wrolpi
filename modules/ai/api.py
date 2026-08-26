"""The /api/ai blueprint — read-only, LLM-shaped endpoints.

This blueprint IS the AI tool catalog: the agent loop generates its tool definitions from these
endpoints' OpenAPI operations, and the external MCP server proxies them.  Every endpoint is
read-only; descriptions are written for the model, not for humans.
"""
from http import HTTPStatus

from sanic import Blueprint, Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from modules.archive import lib as archive_lib
from modules.docs.lib import _doc_response, _get_doc, _search_docs
from modules.inventory.common import get_inventory_configs
from modules.inventory.errors import UnknownInventory
from modules.videos.video import lib as videos_lib
from modules.zim import lib as zim_lib
from wrolpi import flags
from wrolpi.api_utils import json_response
from wrolpi.collections.lib import search_collections
from wrolpi.common import api_param_limiter, get_media_directory, logger, wrol_mode_enabled
from wrolpi.downloader import download_manager
from wrolpi.errors import InvalidFile, SearchEmpty, UnknownFile, ValidationError
from wrolpi.files.lib import search_files
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


def _offset(request: Request) -> int:
    try:
        return max(int(request.args.get('offset', 0)), 0)
    except ValueError:
        return 0


@ai_bp.post('/search')
@openapi.definition(
    summary='Search all WROLPi content',
    description='Search everything in the library at once: videos, archived web pages, ebooks, PDFs, and other'
                ' files. Returns lean results with a WROLPi link for each item. Prefer the type-specific search'
                ' (videos/archives/docs) when the user asks about one kind of content. When total is large,'
                ' narrow the query instead of paging.',
    body=schema.AISearchRequest,
)
@openapi.operation('search_all')
@openapi.response(HTTPStatus.OK, schema.AISearchResponse)
@validate(schema.AISearchRequest)
async def search_all(_: Request, body: schema.AISearchRequest):
    file_groups, total = search_files(
        body.search_str,
        ai_limiter(body.limit),
        body.offset or 0,
        mimetypes=body.mimetypes,
        tag_names=body.tag_names,
        headline=True,
    )
    return json_response(lib.format_file_groups(file_groups, total))


@ai_bp.post('/videos/search')
@openapi.definition(
    summary='Search videos',
    description='Search downloaded videos (and audio) by title and captions. Returns lean results with a'
                ' WROLPi link and a captions_link for each video. When total is large, narrow the query'
                ' instead of paging.',
    body=schema.AIVideoSearchRequest,
)
@openapi.operation('search_videos')
@openapi.response(HTTPStatus.OK, schema.AISearchResponse)
@validate(schema.AIVideoSearchRequest)
async def search_videos(_: Request, body: schema.AIVideoSearchRequest):
    file_groups, total = videos_lib.search_videos(
        search_str=body.search_str,
        offset=body.offset or 0,
        limit=ai_limiter(body.limit),
        channel_id=body.channel_id,
        tag_names=body.tag_names,
        headline=True,
    )
    return json_response(lib.format_file_groups(file_groups, total))


@ai_bp.get('/videos/<file_group_id:int>')
@openapi.definition(
    summary='Get one video',
    description='Get details about one video by its ID from search results: title, channel, description,'
                ' duration, link, and a captions_link to read what is said in the video.',
)
@openapi.operation('get_video')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_video(_: Request, file_group_id: int):
    video, _prev, _next = videos_lib.get_video_for_app(file_group_id, skip_viewed=True)
    result = lib.format_file_group(video, description_length=lib.DETAIL_DESCRIPTION_LENGTH)
    return json_response(result)


@ai_bp.get('/videos/<file_group_id:int>/captions')
@openapi.definition(
    summary='Get video captions',
    description='Read the timestamped captions of a video by its ID; use this to learn what is said in a video'
                ' without watching it. Long captions are paged: request again with offset=next_offset to'
                ' continue reading.',
)
@openapi.operation('get_video_captions')
@openapi.parameter('offset', int, 'query')
@openapi.response(HTTPStatus.OK, schema.AIPagedTextResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_video_captions(request: Request, file_group_id: int):
    video = videos_lib.get_video(file_group_id)
    text = lib.format_caption_chunks(video.get_caption_chunks())
    return json_response(lib.paginate_text(text, _offset(request)))


@ai_bp.get('/videos/<file_group_id:int>/comments')
@openapi.definition(
    summary='Get video comments',
    description='Read the downloaded comments of a video by its ID. Long comment threads are paged:'
                ' request again with offset=next_offset to continue reading.',
)
@openapi.operation('get_video_comments')
@openapi.parameter('offset', int, 'query')
@openapi.response(HTTPStatus.OK, schema.AIPagedTextResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_video_comments(request: Request, file_group_id: int):
    video = videos_lib.get_video(file_group_id)
    comments = video.get_comments() or []
    lines = []
    for comment in comments:
        author = comment.get('author') or 'unknown'
        text = (comment.get('text') or '').strip()
        if text:
            lines.append(f'{author}: {text}')
    return json_response(lib.paginate_text('\n'.join(lines), _offset(request)))


@ai_bp.post('/archives/search')
@openapi.definition(
    summary='Search archived web pages',
    description='Search archived web pages (saved with SingleFile) by title and content. Returns lean results'
                ' with a WROLPi link and a text_link to read each page. Filter with domain (e.g. "example.com")'
                ' when the user asks about one site.',
    body=schema.AIArchiveSearchRequest,
)
@openapi.operation('search_archives')
@openapi.response(HTTPStatus.OK, schema.AISearchResponse)
@validate(schema.AIArchiveSearchRequest)
async def search_archives(_: Request, body: schema.AIArchiveSearchRequest):
    file_groups, total = archive_lib.search_archives(
        body.search_str,
        body.domain,
        ai_limiter(body.limit),
        body.offset or 0,
        None,  # order: default (most recently published)
        body.tag_names,
        headline=True,
    )
    return json_response(lib.format_file_groups(file_groups, total))


@ai_bp.get('/archives/<file_group_id:int>')
@openapi.definition(
    summary='Get one archived web page',
    description='Get details about one archived web page by its ID from search results: title, source URL,'
                ' its WROLPi link, a text_link to read it, and earlier snapshots of the same page.',
)
@openapi.operation('get_archive')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_archive(request: Request, file_group_id: int):
    archive = archive_lib.get_archive_by_file_group_id(request.ctx.session, file_group_id, skip_viewed=True)
    result = lib.format_file_group(archive.file_group.__json__(),
                                   description_length=lib.DETAIL_DESCRIPTION_LENGTH)
    history = []
    for snapshot in archive.history[:10]:
        fg = snapshot.file_group.__json__()
        history.append({k: v for k, v in dict(
            id=fg.get('id'),
            title=fg.get('title') or fg.get('name'),
            published=fg.get('published_datetime'),
            link=lib.wrolpi_link(fg),
        ).items() if v is not None})
    if history:
        result['history'] = history
    return json_response(result)


@ai_bp.get('/archives/<file_group_id:int>/text')
@openapi.definition(
    summary='Read an archived web page',
    description='Read the plain text content of an archived web page by its ID. Long pages are paged: request'
                ' again with offset=next_offset to continue reading.',
)
@openapi.operation('get_archive_text')
@openapi.parameter('offset', int, 'query')
@openapi.response(HTTPStatus.OK, schema.AIPagedTextResponse)
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_archive_text(request: Request, file_group_id: int):
    archive = archive_lib.get_archive_by_file_group_id(request.ctx.session, file_group_id, skip_viewed=True)
    text = lib.read_archive_text(archive)
    if text is None:
        raise UnknownFile(f'No readable text for archive {file_group_id}')
    return json_response(lib.paginate_text(text, _offset(request)))


@ai_bp.post('/docs/search')
@openapi.definition(
    summary='Search documents and ebooks',
    description='Search documents (ebooks, PDFs, comics, office docs) by title, content, author, or subject.'
                ' Returns lean results with a WROLPi link for each document. Provide at least one of'
                ' search_str, author, subject, or tag_names.',
    body=schema.AIDocSearchRequest,
)
@openapi.operation('search_docs')
@openapi.response(HTTPStatus.OK, schema.AISearchResponse)
@validate(schema.AIDocSearchRequest)
async def search_docs(_: Request, body: schema.AIDocSearchRequest):
    file_groups, total = _search_docs(
        search_str=body.search_str,
        author=body.author,
        subject=body.subject,
        language=body.language,
        mimetype=body.mimetype,
        limit=ai_limiter(body.limit),
        offset=body.offset or 0,
        order_by='rank' if body.search_str else 'published_datetime',
        tag_names=body.tag_names,
    )
    return json_response(lib.format_file_groups(file_groups, total))


@ai_bp.get('/docs/<file_group_id:int>')
@openapi.definition(
    summary='Get one document',
    description='Get details about one document (ebook, PDF, comic, etc.) by its ID from search results:'
                ' title, author, subject, description, and its WROLPi link.',
)
@openapi.operation('get_doc')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_doc(request: Request, file_group_id: int):
    doc = _get_doc(request.ctx.session, file_group_id)
    response = _doc_response(doc)
    file_group = response['file_group']
    # Merge the Doc's details into the FileGroup dict so the lean formatter can use them.
    file_group['doc'] = response['doc']
    result = lib.format_file_group(file_group, description_length=lib.DETAIL_DESCRIPTION_LENGTH)
    return json_response(result)


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
    description='Search Zim encyclopedias (Wikipedia, etc.). Without zim_id this searches only the Zims that'
                ' have search-by-default enabled; pass zim_id (from list_zims) to search one specific Zim.'
                ' Use the returned link (or zim_id and path) to read a full entry.',
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
    description='Read one article from a Zim encyclopedia as plain text. Pass the path from Zim search'
                ' results. Long articles are paged: request again with offset=next_offset to continue'
                ' reading.',
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
    description='List collections in the library. Filter with kind: "channel" (video channels), "domain"'
                ' (archived websites), or "playlist". Use a channel\'s id with search_videos, or a domain\'s'
                ' name with search_archives.',
)
@openapi.operation('list_collections')
@openapi.parameter('kind', str, 'query')
async def list_collections(request: Request):
    kind = request.args.get('kind')
    collections = search_collections(request.ctx.session, kind=kind)
    results = []
    for collection in collections:
        results.append({k: v for k, v in dict(
            id=collection.get('id'),
            name=collection.get('name'),
            kind=collection.get('kind'),
            directory=collection.get('directory'),
        ).items() if v is not None})
    return json_response(dict(results=results, total=len(results)))


@ai_bp.get('/inventories')
@openapi.definition(
    summary='List inventories',
    description='List the inventories (food storage, emergency supplies, etc.). Use the slug with'
                ' get_inventory to read the items.',
)
@openapi.operation('list_inventories')
async def list_inventories(_: Request):
    inventories = get_inventory_configs().all_inventories()
    results = [{k: v for k, v in dict(
        slug=i.get('slug'),
        name=i.get('name'),
        type=i.get('type'),
        item_count=len(i.get('items') or []),
    ).items() if v is not None} for i in inventories]
    return json_response(dict(results=results, total=len(results)))


@ai_bp.get('/inventories/<slug:str>')
@openapi.definition(
    summary='Get one inventory',
    description='Get one inventory in full (its fields and every item) by its slug from list_inventories.',
)
@openapi.operation('get_inventory')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_inventory(_: Request, slug: str):
    inventory = get_inventory_configs().get_inventory(slug)
    if inventory is None:
        raise UnknownInventory(f'No inventory: {slug}')
    return json_response(dict(inventory=inventory))


# ---------------------------------------------------------------------------
# Help endpoints (Help mode).  Help markdown is searched in-process; see help_docs.py.
# ---------------------------------------------------------------------------

@ai_bp.post('/help/search')
@openapi.definition(
    summary='Search the WROLPi help documentation',
    description='Search the WROLPi help documentation for how to use and repair WROLPi. Returns matching'
                ' help pages with a snippet; read a full page with get_help_doc. Links are pages on the'
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


@ai_bp.get('/files/read')
@openapi.definition(
    summary='Read a text file',
    description='Read a plain-text file from the media directory by its relative path (from search result'
                ' links or collection directories). Only text files can be read. Long files are paged:'
                ' request again with offset=next_offset to continue reading.',
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

    media_directory = get_media_directory().resolve()
    path = (media_directory / relative.lstrip('/')).resolve()
    if not str(path).startswith(f'{media_directory}/'):
        raise InvalidFile('Cannot read outside the media directory')
    # The config directory can contain secrets (Wi-Fi credentials, API keys); never serve it.
    if str(path).startswith(f'{media_directory / "config"}/'):
        raise InvalidFile('Cannot read config files')
    if not path.is_file():
        raise UnknownFile(f'No such file: {relative}')
    if path.stat().st_size > MAX_TEXT_FILE_SIZE:
        raise InvalidFile('File is too large to read')

    data = path.read_bytes()
    if b'\x00' in data[:8192]:
        raise InvalidFile('Not a text file')
    return json_response(lib.paginate_text(data.decode('UTF-8', errors='replace'), _offset(request)))
