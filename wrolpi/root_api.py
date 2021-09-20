import logging
import re
from http import HTTPStatus

from pytz import UnknownTimeZoneError
from sanic import Sanic, response, Blueprint
from sanic.request import Request
from sanic_cors import CORS
from sanic_openapi import swagger_blueprint

from wrolpi.common import EVENTS, set_sanic_url_parts, logger, get_config, json_response, \
    wrol_mode_enabled, set_timezone, save_settings_config
from wrolpi.errors import WROLModeEnabled, InvalidTimezone
from wrolpi.schema import RegexRequest, RegexResponse, SettingsRequest, SettingsResponse, EchoResponse, \
    EventsResponse, validate_doc

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

root_api = Blueprint('Root API', url_prefix='/api')

# Attach the Sanic OpenAPI blueprint to the API App.  This will generate our API docs.
BLUEPRINTS = [swagger_blueprint, root_api, ]


def get_blueprint(name: str, url_prefix: str) -> Blueprint:
    """
    Create a new Sanic blueprint.  This will be attached to the app just before run.  See `root_api.run_webserver`.
    """
    bp = Blueprint(name, url_prefix)
    add_blueprint(bp)
    return bp


def add_blueprint(bp: Blueprint):
    BLUEPRINTS.append(bp)


def run_webserver(host: str, port: int, workers: int = 8):
    set_sanic_url_parts(host, port)

    # Attach all blueprints after they have been defined.
    for bp in BLUEPRINTS:
        api_app.blueprint(bp)

    # Sanic should match our logging level.
    debug = logger.level == logging.DEBUG
    # TODO remove the auto reload when development is stable
    api_app.run(host, port, workers=workers, debug=debug, auto_reload=True)


def init_parser(parser):
    # Called by WROLPI's main() function
    parser.add_argument('-H', '--host', default=DEFAULT_HOST, help='What network interface to connect webserver')
    parser.add_argument('-p', '--port', default=DEFAULT_PORT, type=int, help='What port to connect webserver')
    parser.add_argument('-w', '--workers', default=4, type=int, help='How many web workers to run')


def main(args):
    run_webserver(args.host, args.port, args.workers)
    return 0


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


@root_api.get('/events')
@validate_doc(
    summary='Get a list of event feeds',
    produces=EventsResponse,
)
def events(_: Request):
    e = [{'name': name, 'is_set': event.is_set()} for (name, event) in EVENTS]
    return response.json({'events': e})


# TODO the following needs to be moved to their respective services.

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
