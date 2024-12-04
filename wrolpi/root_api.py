import asyncio
import pathlib
import re
from http import HTTPStatus

import vininfo.exceptions
from sanic import response, Blueprint, __version__ as sanic_version
from sanic.request import Request
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi
from vininfo import Vin
from vininfo.details._base import VinDetails

from modules.archive.api import archive_bp
from modules.inventory import inventory_bp
from modules.map.api import map_bp
from modules.otp.api import otp_bp
from modules.videos.api import videos_bp
from modules.zim.api import zim_bp
from wrolpi import admin, flags, schema, dates
from wrolpi import tags
from wrolpi.admin import HotspotStatus
from wrolpi.api_utils import json_response, api_app
from wrolpi.common import logger, get_wrolpi_config, wrol_mode_enabled, get_media_directory, \
    wrol_mode_check, native_only, disable_wrol_mode, enable_wrol_mode, get_global_statistics, url_strip_host, \
    set_global_log_level, get_relative_to_media_directory, search_other_estimates
from wrolpi.config_api import config_bp
from wrolpi.dates import now
from wrolpi.db import get_db_session
from wrolpi.downloader import download_manager
from wrolpi.errors import WROLModeEnabled, HotspotError, HotspotPasswordTooShort, InvalidConfig, \
    ValidationError
from wrolpi.events import get_events, Events
from wrolpi.files import files_bp
from wrolpi.files.lib import get_file_statistics, search_file_suggestion_count
from wrolpi.tags import Tag
from wrolpi.vars import DOCKERIZED, IS_RPI, IS_RPI4, IS_RPI5, API_HOST, API_PORT, API_WORKERS, API_DEBUG, \
    API_ACCESS_LOG, truthy_arg, API_AUTO_RELOAD
from wrolpi.version import __version__

logger = logger.getChild(__name__)

api_app.config.FALLBACK_ERROR_FORMAT = 'json'

api_bp = Blueprint('RootAPI', url_prefix='/api')

# Blueprints order here defines what order they are displayed in OpenAPI Docs.
api_app.blueprint(api_bp)
api_app.blueprint(archive_bp)
api_app.blueprint(config_bp)
api_app.blueprint(files_bp)
api_app.blueprint(inventory_bp)
api_app.blueprint(map_bp)
api_app.blueprint(otp_bp)
api_app.blueprint(videos_bp)
api_app.blueprint(zim_bp)


def run_webserver(
        host: str = API_HOST,
        port: int = API_PORT,
        workers: int = API_WORKERS,
        api_debug: bool = API_DEBUG,
        access_log: bool = API_ACCESS_LOG,
):
    # Attach all blueprints after they have been defined.

    kwargs = dict(
        host=host,
        port=port,
        workers=workers,
        debug=api_debug,
        access_log=access_log,
        auto_reload=DOCKERIZED,
    )
    logger.warning(f'Running Sanic {sanic_version} with kwargs {kwargs}')
    return api_app.run(**kwargs)


def init_parser(parser):
    # Called by WROLPI's main() function
    parser.add_argument('-H', '--host', default=API_HOST, help='What network interface to connect webserver')
    parser.add_argument('-p', '--port', default=API_PORT, type=int, help='What port to connect webserver')
    parser.add_argument('-w', '--workers', default=API_WORKERS, type=int, help='How many web workers to run')
    parser.add_argument('--access-log', default=API_ACCESS_LOG, type=truthy_arg, help='Enable Sanic access log')
    parser.add_argument('--api-debug', default=API_DEBUG, type=truthy_arg, help='Enable Sanic debug log')
    parser.add_argument('--api-auto-reload', default=API_AUTO_RELOAD, type=truthy_arg, help='Enable Sanic auto reload')


def main(args):
    return run_webserver(
        host=args.host,
        port=args.port,
        workers=args.workers,
        api_debug=args.api_debug,
        access_log=args.access_log,
    )


index_html = '''
<html>
<body>
<p>
    This is a WROLPi API.
    <ul>
        <li>You can test it at this endpoint <a href="/api/echo">/api/echo</a></li>
        <li>You can view the docs at <a href="/docs">/docs</a></li>
    </ul>
</p>
</body>
</html>
'''


@api_app.get('/')
@api_bp.get('/')
async def index(_):
    return response.html(index_html)


@api_bp.route('/echo', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@openapi.definition(
    description='Echo whatever is sent to this.',
    response=schema.EchoResponse,
)
async def echo(request: Request):
    try:
        request_json = request.json
    except Exception as e:
        logger.error('Failed to parse request JSON', exc_info=e)
        request_json = None
    request_headers = dict(request.headers)
    ret = dict(
        form=request.form,
        headers=request_headers,
        json=request_json,
        method=request.method,
        args=request.args,
    )
    return response.json(ret)


@api_bp.route('/settings', methods=['GET', 'OPTIONS'])
@openapi.definition(
    description='Get WROLPi settings',
    response=schema.SettingsResponse,
)
def get_settings(_: Request):
    wrolpi_config = get_wrolpi_config()

    ignored_directories = [get_relative_to_media_directory(i) for i in wrolpi_config.ignored_directories]

    settings = {
        'archive_destination': wrolpi_config.archive_destination,
        'download_manager_disabled': download_manager.is_disabled,
        'download_manager_stopped': download_manager.is_stopped,
        'download_on_startup': wrolpi_config.download_on_startup,
        'download_timeout': wrolpi_config.download_timeout,
        'hotspot_device': wrolpi_config.hotspot_device,
        'hotspot_on_startup': wrolpi_config.hotspot_on_startup,
        'hotspot_password': wrolpi_config.hotspot_password,
        'hotspot_ssid': wrolpi_config.hotspot_ssid,
        'hotspot_status': admin.hotspot_status().name,
        'ignore_outdated_zims': wrolpi_config.ignore_outdated_zims,
        'ignored_directories': ignored_directories,
        'log_level': api_app.shared_ctx.log_level.value,
        'map_destination': wrolpi_config.map_destination,
        'nav_color': wrolpi_config.nav_color,
        'media_directory': str(get_media_directory()),  # Convert to string to avoid conversion to relative.
        'throttle_on_startup': wrolpi_config.throttle_on_startup,
        'throttle_status': admin.throttle_status().name,
        'version': __version__,
        'videos_destination': wrolpi_config.videos_destination,
        'wrol_mode': wrolpi_config.wrol_mode,
        'zims_destination': wrolpi_config.zims_destination,
    }
    return json_response(settings)


@api_bp.patch('/settings')
@openapi.definition(
    description='Update WROLPi settings',
    body=schema.SettingsRequest,
    validate=True,
)
async def update_settings(_: Request, body: schema.SettingsRequest):
    if wrol_mode_enabled() and body.wrol_mode is None:
        # Cannot update settings while WROL Mode is enabled, unless you want to disable WROL Mode.
        raise WROLModeEnabled()

    if body.wrol_mode is False:
        # Disable WROL Mode
        await disable_wrol_mode()
        return response.empty()
    elif body.wrol_mode is True:
        # Enable WROL Mode
        enable_wrol_mode()
        return response.empty()

    if body.hotspot_password and len(body.hotspot_password) < 8:
        raise HotspotPasswordTooShort()

    # Remove any keys with None values, then save the config.
    new_config = {k: v for k, v in body.__dict__.items() if v is not None}
    wrolpi_config = get_wrolpi_config()

    if not new_config:
        raise InvalidConfig()

    if body.archive_destination and pathlib.Path(body.archive_destination).is_absolute():
        raise InvalidConfig('Archive directory must be relative to media directory')
    elif not body.archive_destination:
        new_config['archive_destination'] = wrolpi_config.default_config['archive_destination']

    if body.videos_destination and pathlib.Path(body.videos_destination).is_absolute():
        raise InvalidConfig('Videos directory must be relative to media directory')
    elif not body.videos_destination:
        new_config['videos_destination'] = wrolpi_config.default_config['videos_destination']

    if body.map_destination and pathlib.Path(body.map_destination).is_absolute():
        raise InvalidConfig('Map directory must be relative to media directory')
    elif not body.map_destination:
        new_config['map_destination'] = wrolpi_config.default_config['map_destination']

    if body.zims_destination and pathlib.Path(body.zims_destination).is_absolute():
        raise InvalidConfig('Zims directory must be relative to media directory')
    elif not body.zims_destination:
        new_config['zims_destination'] = wrolpi_config.default_config['zims_destination']

    log_level = new_config.pop('log_level', None)
    if isinstance(log_level, int):
        set_global_log_level(log_level)

    old_password = wrolpi_config.hotspot_password
    wrolpi_config.update(new_config)

    # If the password was changed, we need to restart the hotspot.
    password_changed = (new_password := new_config.get('hotspot_password')) and old_password != new_password

    if body.hotspot_status is True or (password_changed and admin.hotspot_status() == HotspotStatus.connected):
        # Turn on Hotspot
        if admin.enable_hotspot() is False:
            raise HotspotError('Could not turn on hotspot')
    elif body.hotspot_status is False:
        # Turn off Hotspot
        if admin.disable_hotspot() is False:
            raise HotspotError('Could not turn off hotspot')

    return response.empty()


@api_bp.post('/valid_regex')
@openapi.definition(
    description='Check if the regex is valid.',
    body=schema.RegexRequest,
    response=schema.RegexResponse,
    validate=True,
)
def valid_regex(_: Request, body: schema.RegexRequest):
    try:
        re.compile(body.regex)
        return response.json({'valid': True, 'regex': body.regex})
    except re.error:
        return response.json({'valid': False, 'regex': body.regex}, HTTPStatus.BAD_REQUEST)


@api_bp.post('/download')
@openapi.definition(
    description='Download all the URLs that are provided.',
    body=schema.DownloadRequest,
    validate=True,
)
@wrol_mode_check
async def post_download(_: Request, body: schema.DownloadRequest):
    # Raises an InvalidDownload if the Downloader cannot be found.
    download_manager.find_downloader_by_name(body.downloader)

    kwargs = dict(downloader_name=body.downloader,
                  sub_downloader_name=body.sub_downloader, reset_attempts=True,
                  destination=body.destination, tag_names=body.tag_names,
                  settings=body.settings)
    if body.frequency:
        download_manager.recurring_download(body.urls[0], body.frequency, **kwargs)
    else:
        download_manager.create_downloads(body.urls, **kwargs)
    if download_manager.disabled.is_set() or download_manager.stopped.is_set():
        # Downloads are disabled, warn the user.
        Events.send_downloads_disabled('Download created. But, downloads are disabled.')

    return response.empty(status=HTTPStatus.CREATED)


@api_bp.put('/download/<download_id:int>')
@openapi.definition(
    description='Update properties of the Download',
    body=schema.DownloadRequest,
    validate=True,
)
@wrol_mode_check
async def put_download(_: Request, download_id: int, body: schema.DownloadRequest):
    # Raises an InvalidDownload if the Downloader cannot be found.
    download_manager.find_downloader_by_name(body.downloader)

    if len(body.urls) != 1:
        raise ValidationError('Only one URL can be specified when updating a Download')

    with get_db_session(commit=True) as session:
        download_manager.update_download(
            id_=download_id,
            url=body.urls[0],
            downloader=body.downloader,
            destination=body.destination,
            frequency=body.frequency,
            tag_names=body.tag_names,
            sub_downloader=body.sub_downloader,
            settings=body.settings,
            session=session,
        )
    if download_manager.disabled.is_set() or download_manager.stopped.is_set():
        # Downloads are disabled, warn the user.
        Events.send_downloads_disabled('Download created. But, downloads are disabled.')

    return response.empty()


@api_bp.delete('/download/<download_id:int>')
@openapi.description('Delete a download')
@wrol_mode_check
async def delete_download(_: Request, download_id: int):
    deleted = download_manager.delete_download(download_id)
    return response.empty(HTTPStatus.NO_CONTENT if deleted else HTTPStatus.NOT_FOUND)


@api_bp.post('/download/<download_id:int>/restart')
@openapi.description('Restart a download.')
async def restart_download(_: Request, download_id: int):
    download_manager.restart_download(download_id)
    return response.empty()


@api_bp.get('/download')
@openapi.description('Get all Downloads so they can be displayed to the User.')
async def get_downloads(_: Request):
    data = download_manager.get_fe_downloads()

    # Convert `destination` to relative.
    for download in data['once_downloads']:
        download['destination'] = get_relative_to_media_directory(download['destination']) \
            if download['destination'] else None
    for download in data['recurring_downloads']:
        download['destination'] = get_relative_to_media_directory(download['destination']) \
            if download['destination'] else None

    return json_response(data)


@api_bp.post('/download/<download_id:int>/kill')
@openapi.description('Kill a download.  It will be stopped if it is pending.')
async def kill_download(_: Request, download_id: int):
    download_manager.kill_download(download_id)
    return response.empty()


@api_bp.post('/download/kill')
@openapi.description('Kill all downloads.  Disable downloading.')
async def kill_downloads(_: Request):
    logger.warning('Disabled downloads')
    download_manager.disable()
    return response.empty()


@api_bp.post('/download/enable')
@openapi.description('Enable and start downloading.')
async def enable_downloads(_: Request):
    await download_manager.enable()
    return response.empty()


@api_bp.post('/download/clear_completed')
@openapi.description('Clear completed downloads')
async def clear_completed(_: Request):
    download_manager.delete_completed()
    return response.empty()


@api_bp.post('/download/clear_failed')
@openapi.description('Clear failed downloads')
async def clear_failed(_: Request):
    download_manager.delete_failed()
    return response.empty()


@api_bp.post('/download/retry_once')
@openapi.description('Retry failed once-downloads')
async def retry_once(_: Request):
    download_manager.retry_downloads(reset_attempts=True)
    return response.empty()


@api_bp.post('/download/delete_once')
@openapi.description('Delete all once downloads')
async def delete_once(_: Request):
    download_manager.delete_once()
    return response.empty()


@api_bp.get('/downloaders')
@openapi.description('List all Downloaders that can be specified by the user.')
async def get_downloaders(_: Request):
    downloaders = download_manager.list_downloaders()
    disabled = download_manager.disabled.is_set()
    ret = dict(downloaders=downloaders, manager_disabled=disabled)
    return json_response(ret)


@api_bp.post('/hotspot/on')
@openapi.description('Turn on the hotspot')
@native_only
async def hotspot_on(_: Request):
    result = admin.enable_hotspot(overwrite=True)
    if result:
        return response.empty()
    return response.empty(HTTPStatus.INTERNAL_SERVER_ERROR)


@api_bp.post('/hotspot/off')
@openapi.description('Turn off the hotspot')
@native_only
async def hotspot_off(_: Request):
    result = admin.disable_hotspot()
    if result:
        return response.empty()
    return response.empty(HTTPStatus.INTERNAL_SERVER_ERROR)


@api_bp.post('/throttle/on')
@openapi.description('Turn on CPU throttling')
@native_only
async def throttle_on(_: Request):
    result = admin.throttle_cpu_on()
    if result:
        return response.empty()
    return response.empty(HTTPStatus.INTERNAL_SERVER_ERROR)


@api_bp.post('/throttle/off')
@openapi.description('Turn off CPU throttling')
@native_only
async def throttle_off(_: Request):
    result = admin.throttle_cpu_off()
    if result:
        return response.empty()
    return response.empty(HTTPStatus.INTERNAL_SERVER_ERROR)


@api_bp.get('/status')
@openapi.definition(
    description='Get the status of CPU/load/etc.',
    response=schema.StatusResponse,
)
async def get_status(request: Request):
    downloads = dict()
    if flags.db_up.is_set():
        try:
            downloads = download_manager.get_summary()
        except Exception as e:
            logger.debug('Unable to get download status', exc_info=e)

    sanic_workers = dict()
    if hasattr(request.app, 'multiplexer'):
        # `multiplexer` may be empty while testing.
        sanic_workers = {
            i: {'pid': j['pid'], 'state': j['state']}
            for i, j in request.app.multiplexer.workers.items()
            if i.startswith('Sanic-Server')
        }

    ret = dict(
        dockerized=DOCKERIZED,
        downloads=downloads,
        flags=flags.get_flags(),
        hotspot_ssid=admin.get_current_ssid(get_wrolpi_config().hotspot_device),
        hotspot_status=admin.hotspot_status().name,
        is_rpi4=IS_RPI4,
        is_rpi5=IS_RPI5,
        is_rpi=IS_RPI,
        sanic_workers=sanic_workers,
        throttle_status=admin.throttle_status().name,
        version=__version__,
        wrol_mode=wrol_mode_enabled(),
        # Include all stats from status worker.
        **api_app.shared_ctx.status,
    )
    return json_response(ret)


@api_bp.get('/statistics')
@openapi.definition(
    description='Get summary statistics of all files',
)
async def get_statistics(_):
    file_statistics = get_file_statistics()
    global_statistics = get_global_statistics()
    return json_response({
        'file_statistics': file_statistics,
        'global_statistics': global_statistics,
    })


@api_bp.get('/events/feed')
@openapi.description('Get all events after the provided date.')
@validate(query=schema.EventsRequest)
async def feed(request: Request, query: schema.EventsRequest):
    # Get the current datetime from the API.  The frontend will use this to request any events that happen after it's
    # previous request.  The API decides what the time is, just in case the RPi's clock is wrong, or no NTP is
    # available.
    start = now()

    after = None if query.after == 'None' else dates.strpdate(query.after)
    events = get_events(after)
    return json_response(dict(events=events, now=start))


@api_bp.get('/tag')
@openapi.definition(
    description='Get a list of all Tags',
)
async def get_tags_request(_: Request):
    tags_ = tags.get_tags()
    return json_response(dict(tags=tags_))


@api_bp.post('/tag', name='tag_crate')
@api_bp.post('/tag/<tag_id:int>', name='tag_update')
@openapi.definition(
    description='Create or update a Tag',
    body=schema.TagRequest,
    validate=True,
)
async def post_tag(_: Request, body: schema.TagRequest, tag_id: int = None):
    await tags.upsert_tag(body.name, body.color, tag_id)
    if tag_id:
        return response.empty(HTTPStatus.OK)
    else:
        return response.empty(HTTPStatus.CREATED)


@api_bp.delete('/tag/<tag_id:int>')
async def delete_tag_request(_: Request, tag_id: int):
    Tag.find_by_id(tag_id).delete()
    return response.empty()


@api_bp.post('/notify')
@validate(schema.NotifyRequest)
async def post_notify(_: Request, body: schema.NotifyRequest):
    """Sends a notify Event"""
    url = url_strip_host(body.url)
    Events.send_user_notify(body.message, url)
    return response.empty(HTTPStatus.CREATED)


@api_bp.post('/vin_number_decoder')
@openapi.definition(
    description='Decode a VIN number',
    body=schema.VINDecoderRequest,
    response=schema.VINDecoderResponse,
    validate=True,
)
async def post_vin_number_decoder(_: Request, body: schema.VINDecoderRequest):
    try:
        vin = Vin(body.vin_number)
    except vininfo.exceptions.VininfoException:
        return json_response({}, HTTPStatus.BAD_REQUEST)

    def detail_to_json(details: VinDetails, key: str):
        if details:
            attr = getattr(details, key)
            if attr and attr.name:
                name = attr.name
                if isinstance(name, list):
                    return ', '.join(str(i) for i in name)
                else:
                    return name

    vin = schema.VIN(
        country=vin.country,
        manufacturer=vin.manufacturer,
        region=vin.region,
        years=','.join(map(str, vin.years)),
        body=detail_to_json(vin.details, 'body'),
        engine=detail_to_json(vin.details, 'engine'),
        model=detail_to_json(vin.details, 'model'),
        plant=detail_to_json(vin.details, 'plant'),
        transmission=detail_to_json(vin.details, 'transmission'),
        serial=detail_to_json(vin.details, 'serial'),
    )
    return json_response(dict(vin=vin))


@api_bp.post('/restart')
@openapi.definition(description='Restart the system')
@native_only
async def post_restart(_: Request):
    await admin.shutdown(reboot=True)
    return response.empty(HTTPStatus.NO_CONTENT)


@api_bp.post('/shutdown')
@openapi.definition(description='Shutdown the system')
@native_only
async def post_shutdown(_: Request):
    await admin.shutdown()
    return response.empty(HTTPStatus.NO_CONTENT)


@api_bp.post('/search_suggestions')
@openapi.definition(
    description='Suggest related Channels/Domains/etc. to the user.',
    body=schema.SearchSuggestionsRequest,
    validate=True,
)
async def post_search_suggestions(_: Request, body: schema.SearchSuggestionsRequest):
    from modules.videos.channel.lib import search_channels_by_name
    from modules.archive.lib import search_domains_by_name

    channels, domains = await asyncio.gather(
        search_channels_by_name(body.search_str, order_by_video_count=body.order_by_video_count),
        search_domains_by_name(body.search_str),
    )

    ret = dict(
        channels=channels,
        domains=domains,
    )
    return json_response(ret)


@api_bp.post('/search_file_estimates')
@openapi.definition(
    description='Get a count of FileGroup suggestions.',
    body=schema.SearchFileEstimateRequest,
    validate=True,
)
async def post_search_file_estimates(_: Request, body: schema.SearchFileEstimateRequest):
    """Used by the Global search to suggest FileGroup count to the user."""
    file_groups = await search_file_suggestion_count(
        body.search_str,
        body.tag_names,
        body.mimetypes,
        body.months,
        body.from_year,
        body.to_year,
        body.any_tag,
    )

    ret = dict(
        file_groups=file_groups,
    )
    return json_response(ret)


@api_bp.post('/search_other_estimates')
@openapi.definition(
    description='Get a count of other suggestions.',
    body=schema.SearchOtherEstimateRequest,
    validate=True,
)
async def post_search_other_estimates(_: Request, body: schema.SearchOtherEstimateRequest):
    """Used by the Global search to suggest FileGroup count to the user."""
    others = await search_other_estimates(body.tag_names)
    ret = dict(others=others)
    return json_response(ret)
