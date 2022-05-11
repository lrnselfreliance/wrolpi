import json
import multiprocessing
import re
from datetime import datetime, date
from decimal import Decimal
from functools import wraps
from http import HTTPStatus
from pathlib import Path
from typing import Union

from pytz import UnknownTimeZoneError
from sanic import Sanic, response, Blueprint, __version__ as sanic_version
from sanic.blueprint_group import BlueprintGroup
from sanic.request import Request
from sanic.response import HTTPResponse
from sanic_ext import validate
from sanic_ext.extensions.openapi import openapi

from wrolpi import admin
from wrolpi.common import set_sanic_url_parts, logger, get_config, wrol_mode_enabled, Base, get_media_directory, \
    wrol_mode_check, native_only, set_wrol_mode
from wrolpi.dates import set_timezone
from wrolpi.downloader import download_manager
from wrolpi.errors import WROLModeEnabled, InvalidTimezone, API_ERRORS, APIError, ValidationError, HotspotError
from wrolpi.media_path import MediaPath
from wrolpi.schema import RegexRequest, RegexResponse, SettingsRequest, SettingsResponse, DownloadRequest, EchoResponse
from wrolpi.vars import DOCKERIZED
from wrolpi.version import __version__

logger = logger.getChild(__name__)

api_app = Sanic(name='api_app')

DEFAULT_HOST, DEFAULT_PORT = '127.0.0.1', '8081'

root_api = Blueprint('RootAPI', url_prefix='/api')

BLUEPRINTS = [root_api, ]


def get_blueprint(name: str, url_prefix: str) -> Blueprint:
    """
    Create a new Sanic blueprint.  This will be attached to the app just before run.  See `root_api.run_webserver`.
    """
    bp = Blueprint(name, url_prefix)
    add_blueprint(bp)
    return bp


def add_blueprint(bp: Union[Blueprint, BlueprintGroup]):
    BLUEPRINTS.append(bp)


def run_webserver(loop, host: str, port: int, workers: int = 8):
    set_sanic_url_parts(host, port)

    # Attach all blueprints after they have been defined.
    for bp in BLUEPRINTS:
        api_app.blueprint(bp)

    # TODO remove the auto reload when development is stable
    kwargs = dict(host=host, port=port, workers=workers, auto_reload=DOCKERIZED)
    logger.debug(f'Running Sanic {sanic_version} with kwargs {kwargs}')
    return api_app.run(**kwargs)


def init_parser(parser):
    # Called by WROLPI's main() function
    parser.add_argument('-H', '--host', default=DEFAULT_HOST, help='What network interface to connect webserver')
    parser.add_argument('-p', '--port', default=DEFAULT_PORT, type=int, help='What port to connect webserver')
    parser.add_argument('-w', '--workers', default=multiprocessing.cpu_count(), type=int,
                        help='How many web workers to run')


def main(loop, args):
    return run_webserver(loop, args.host, args.port, args.workers)


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
def index(_):
    return response.html(index_html)


@root_api.route('/echo', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@openapi.description('Echo whatever is sent to this.')
@openapi.response(HTTPStatus.OK, EchoResponse)
async def echo(request: Request):
    ret = dict(
        form=request.form,
        headers=dict(request.headers),
        json=request.json,
        method=request.method,
        args=request.args,
    )
    return response.json(ret)


@root_api.route('/settings', methods=['GET', 'OPTIONS'])
@openapi.description('Get WROLPi settings')
@openapi.response(HTTPStatus.OK, SettingsResponse)
def get_settings(_: Request):
    config = get_config()

    settings = {
        'download_on_startup': config.download_on_startup,
        'hotspot_on_startup': config.hotspot_on_startup,
        'hotspot_password': config.hotspot_password,
        'hotspot_ssid': config.hotspot_ssid,
        'hotspot_status': admin.hotspot_status().name,
        'media_directory': get_media_directory(),
        'throttle_on_startup': config.throttle_on_startup,
        'throttle_status': admin.throttle_status().name,
        'timezone': config.timezone,
        'version': __version__,
        'wrol_mode': config.wrol_mode,
    }
    return json_response(settings)


@root_api.patch('/settings')
@openapi.description('Update WROLPi settings')
@validate(json=SettingsRequest)
def update_settings(_: Request, body: SettingsRequest):
    if wrol_mode_enabled() and body.wrol_mode is None:
        # Cannot update settings while WROL Mode is enabled, unless you want to disable WROL Mode.
        raise WROLModeEnabled()

    if body.wrol_mode is False:
        # Disable WROL Mode
        set_wrol_mode(False)
        return response.empty()
    elif body.wrol_mode is True:
        # Enable WROL Mode
        set_wrol_mode(True)
        return response.empty()

    try:
        if body.timezone:
            set_timezone(body.timezone)
    except UnknownTimeZoneError:
        raise InvalidTimezone(f'Invalid timezone: {body.timezone}')

    # Remove any keys with None values, then save the config.
    config = {k: v for k, v in body.__dict__.items() if v is not None}
    wrolpi_config = get_config()
    wrolpi_config.update(config)

    if body.wrol_mode:
        download_manager.kill()

    if body.hotspot_status is True:
        # Turn on Hotspot
        if admin.enable_hotspot() is False:
            raise HotspotError('Could not turn on hotspot')
    elif body.hotspot_status is False:
        # Turn off Hotspot
        if admin.disable_hotspot() is False:
            raise HotspotError('Could not turn off hotspot')

    return response.empty()


@root_api.post('/valid_regex')
@openapi.description('Check if the regex is valid.')
@openapi.response(HTTPStatus.OK, RegexResponse)
@openapi.response(HTTPStatus.BAD_REQUEST, RegexResponse)
@validate(RegexRequest)
def valid_regex(_: Request, body: RegexRequest):
    try:
        re.compile(body.regex)
        return response.json({'valid': True, 'regex': body.regex})
    except re.error:
        return response.json({'valid': False, 'regex': body.regex}, HTTPStatus.BAD_REQUEST)


@root_api.post('/download')
@openapi.description('Download the many URLs that are provided.')
@validate(DownloadRequest)
@wrol_mode_check
async def post_download(_: Request, body: DownloadRequest):
    # URLs are provided in a textarea, lets split all lines.
    urls = [i.strip() for i in str(body.urls).strip().splitlines()]
    downloader = body.downloader
    if not downloader or downloader in ('auto', 'None', 'null'):
        downloader = None
    download_manager.create_downloads(urls, downloader=downloader, reset_attempts=True)
    return response.empty()


@root_api.get('/download')
@openapi.description('Get all Downloads that need to be processed.')
async def get_downloads(_: Request):
    data = download_manager.get_fe_downloads()
    return json_response(data)


@root_api.post('/download/<download_id:int>/kill')
@openapi.description('Kill a download.  It will be stopped if it is pending.')
async def kill_download(_: Request, download_id: int):
    download_manager.kill_download(download_id)
    return response.empty()


@root_api.post('/download/kill')
@openapi.description('Kill all downloads.  Disable downloading.')
async def kill_downloads(_: Request):
    download_manager.kill()
    return response.empty()


@root_api.post('/download/enable')
@openapi.description('Enable and start downloading.')
async def enable_downloads(_: Request):
    download_manager.enable()
    return response.empty()


@root_api.post('/download/clear_completed')
@openapi.description('Clear completed downloads')
async def clear_completed(_: Request):
    download_manager.delete_completed()
    return response.empty()


@root_api.post('/download/clear_failed')
@openapi.description('Clear failed downloads')
async def clear_failed(_: Request):
    download_manager.delete_failed()
    return response.empty()


@root_api.delete('/download/<download_id:integer>')
@openapi.description('Delete a download')
@wrol_mode_check
async def delete_download(_: Request, download_id: int):
    deleted = download_manager.delete_download(download_id)
    return response.empty(HTTPStatus.NO_CONTENT if deleted else HTTPStatus.NOT_FOUND)


@root_api.get('/downloaders')
@openapi.description('List all Downloaders that can be specified by the user.')
async def get_downloaders(_: Request):
    downloaders = download_manager.list_downloaders()
    disabled = download_manager.disabled.is_set()
    ret = dict(downloaders=downloaders, manager_disabled=disabled)
    return json_response(ret)


@root_api.post('/hotspot/on')
@openapi.description('Turn on the hotspot')
@native_only
async def hotspot_on(_: Request):
    result = admin.enable_hotspot()
    if result:
        return response.empty()
    return response.empty(HTTPStatus.INTERNAL_SERVER_ERROR)


@root_api.post('/hotspot/off')
@openapi.description('Turn off the hotspot')
@native_only
async def hotspot_off(_: Request):
    result = admin.disable_hotspot()
    if result:
        return response.empty()
    return response.empty(HTTPStatus.INTERNAL_SERVER_ERROR)


@root_api.post('/throttle/on')
@openapi.description('Turn on CPU throttling')
@native_only
async def throttle_on(_: Request):
    result = admin.throttle_cpu_on()
    if result:
        return response.empty()
    return response.empty(HTTPStatus.INTERNAL_SERVER_ERROR)


@root_api.post('/throttle/off')
@openapi.description('Turn off CPU throttling')
@native_only
async def throttle_off(_: Request):
    result = admin.throttle_cpu_off()
    if result:
        return response.empty()
    return response.empty(HTTPStatus.INTERNAL_SERVER_ERROR)


class CustomJSONEncoder(json.JSONEncoder):

    def default(self, obj):
        try:
            if hasattr(obj, '__json__'):
                # Get __json__ before others.
                return obj.__json__()
            elif isinstance(obj, datetime):
                return obj.timestamp()
            elif isinstance(obj, date):
                return datetime(obj.year, obj.month, obj.day).timestamp()
            elif isinstance(obj, Decimal):
                return str(obj)
            elif isinstance(obj, Base):
                if hasattr(obj, 'dict'):
                    return obj.dict()
            elif isinstance(obj, Path):
                return str(obj)
            elif isinstance(obj, MediaPath):
                media_directory = get_media_directory()
                path = obj.path.relative_to(media_directory)
                if str(path) == '.':
                    return ''
                return str(path)
            return super(CustomJSONEncoder, self).default(obj)
        except Exception as e:
            logger.fatal(f'Failed to JSON encode {obj}', exc_info=e)
            raise


@wraps(response.json)
def json_response(*a, **kwargs) -> HTTPResponse:
    """
    Handles encoding date/datetime in JSON.
    """
    resp = response.json(*a, **kwargs, cls=CustomJSONEncoder, dumps=json.dumps)
    return resp


def json_error_handler(request, exception: Exception):
    error = API_ERRORS[type(exception)]
    if isinstance(exception, ValidationError):
        body = dict(error='Could not validate the contents of the request', code=error['code'])
    else:
        body = dict(message=str(exception), api_error=error['message'], code=error['code'])
    if cause := exception.__cause__:
        cause = API_ERRORS[type(cause)]
        body['cause'] = dict(error=cause['message'], code=cause['code'])
    return json_response(body, error['status'])


api_app.error_handler.add(APIError, json_error_handler)
