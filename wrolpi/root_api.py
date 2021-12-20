import json
import json
import multiprocessing
import re
from datetime import datetime, date
from decimal import Decimal
from functools import wraps
from http import HTTPStatus
from pathlib import Path

from pytz import UnknownTimeZoneError
from sanic import Sanic, response, Blueprint, __version__ as sanic_version
from sanic.request import Request
from sanic.response import HTTPResponse
from sanic_cors import CORS

from wrolpi.common import set_sanic_url_parts, logger, get_config, wrol_mode_enabled, save_settings_config, \
    Base, get_media_directory, wrol_mode_check
from wrolpi.dates import set_timezone
from wrolpi.downloader import download_manager
from wrolpi.errors import WROLModeEnabled, InvalidTimezone
from wrolpi.media_path import MediaPath
from wrolpi.schema import RegexRequest, RegexResponse, SettingsRequest, SettingsResponse, EchoResponse, \
    validate_doc, DownloadRequest
from wrolpi.vars import DOCKERIZED

logger = logger.getChild(__name__)

api_app = Sanic(name='api_app')

DEFAULT_HOST, DEFAULT_PORT = '127.0.0.1', '8081'

# TODO Allow all requests to this webapp during development.  This should be restricted later.
CORS(
    api_app,
    expose_headers=[
        'Location',  # Expose this header so the App can send users to the location of a created object.
    ],
    resources={
        '/*': {'origins': '*'},
    }
)

root_api = Blueprint('RootAPI', url_prefix='/api')

BLUEPRINTS = [root_api, ]


def get_blueprint(name: str, url_prefix: str) -> Blueprint:
    """
    Create a new Sanic blueprint.  This will be attached to the app just before run.  See `root_api.run_webserver`.
    """
    bp = Blueprint(name, url_prefix)
    add_blueprint(bp)
    return bp


def add_blueprint(bp: Blueprint):
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
        <li>You can view the docs at <a href="/swagger">/swagger</a></li>
    </ul>
</p>
</body>
</html>
'''


@api_app.get('/')
def index(_):
    return response.html(index_html)


@root_api.route('/echo', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@validate_doc(
    summary='Echo whatever is sent to this',
    produces=EchoResponse,
    tag='Testing',
)
async def echo(request: Request):
    """
    Returns a JSON object containing details about the request sent to me.
    """
    ret = dict(
        form=request.form,
        headers=dict(request.headers),
        json=request.json,
        method=request.method,
        args=request.args,
    )
    return response.json(ret)


@root_api.route('/settings', methods=['GET', 'OPTIONS'])
@validate_doc(
    summary='Get WROLPi settings',
    produces=SettingsResponse,
)
def get_settings(_: Request):
    config = dict(get_config())
    return json_response({'config': config})


@root_api.patch('/settings')
@validate_doc(
    summary='Update WROLPi settings',
    consumes=SettingsRequest,
)
def update_settings(_: Request, data: dict):
    if wrol_mode_enabled() and 'wrol_mode' not in data:
        # Cannot update settings while WROL Mode is enabled, unless you want to disable WROL Mode.
        raise WROLModeEnabled()

    try:
        if data.get('timezone'):
            set_timezone(data['timezone'])
    except UnknownTimeZoneError:
        raise InvalidTimezone(f'Invalid timezone: {data["timezone"]}')

    save_settings_config(data)

    return response.raw('', HTTPStatus.NO_CONTENT)


@root_api.post('/valid_regex')
@validate_doc(
    summary='Check if the regex is valid',
    consumes=RegexRequest,
    responses=(
            (HTTPStatus.OK, RegexResponse),
            (HTTPStatus.BAD_REQUEST, RegexResponse),
    )
)
def valid_regex(_: Request, data: dict):
    try:
        re.compile(data['regex'])
        return response.json({'valid': True, 'regex': data['regex']})
    except re.error:
        return response.json({'valid': False, 'regex': data['regex']}, HTTPStatus.BAD_REQUEST)


@root_api.post('/download')
@validate_doc(
    summary='Download the many URLs that are provided.',
    consumes=DownloadRequest,
)
@wrol_mode_check
async def post_download(request: Request, data: dict):
    # URLs are provided in a textarea, lets split all lines.
    urls = [i.strip() for i in str(data['urls']).strip().splitlines()]
    download_manager.create_downloads(urls)
    return response.empty()


@root_api.get('/download')
@validate_doc(
    summary='Get all Downloads that need to be processed.',
)
async def get_downloads(request: Request):
    data = dict(
        recurring_downloads=download_manager.get_recurring_downloads(),
        once_downloads=download_manager.get_once_downloads(limit=1000),
    )
    return json_response(data)


@root_api.post('/download/<download_id:int>/kill')
async def kill_download(request: Request, download_id: int):
    download_manager.kill_download(download_id)
    return response.empty()


@root_api.delete('/download/<download_id:integer>')
@wrol_mode_check
async def delete_download(request: Request, download_id: int):
    deleted = download_manager.delete_download(download_id)
    return response.empty(HTTPStatus.NO_CONTENT if deleted else HTTPStatus.NOT_FOUND)


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
