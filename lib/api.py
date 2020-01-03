import argparse
import logging
import os
import pathlib
from functools import wraps

from dotenv import load_dotenv
from sanic import Blueprint, Sanic, response
from sanic.request import Request
from sanic_cors import CORS
from sanic_openapi import swagger_blueprint, doc

from lib.common import logger, set_sanic_url_parts, validate_doc
from lib.db import get_db
from lib.modules import MODULES

cwd = pathlib.Path(__file__).parent

api_app = Sanic()
# TODO Allow all requests to this webapp during development.  This should be restricted later.
CORS(api_app)

# Attach the Sanic OpenAPI blueprint to the API App.  This will generate our API docs.
api_app.blueprint(swagger_blueprint)

# Load default variables from .env file
load_dotenv()
DEFAULT_URL = os.getenv('REACT_APP_API', '127.0.0.1:8081')
DEFAULT_HOST, DEFAULT_PORT = DEFAULT_URL.split(':')


# Add DB middleware
@api_app.middleware('request')
def setup_db_context(request):
    @wraps(get_db)
    def _get_db():
        pool, conn, db, key = get_db()
        request.ctx.pool = pool
        request.ctx.conn = conn
        request.ctx.db = db
        request.ctx.key = key
        return db

    request.ctx.get_db = _get_db


@api_app.middleware('response')
def teardown_db_context(request, _):
    try:
        pool, conn, key = request.ctx.pool, request.ctx.conn, request.ctx.key
        try:
            pool.putconn(conn, key=key, close=True)
        except KeyError:
            logger.debug(f'Failed to return db connection {key}')
    except AttributeError:
        # get_db was never called
        pass


@api_app.route('/')
def index(request):
    html = '''
    <html>
    <body>
    <p>
        This is the WROLPi API.
        <ul>
            <li>You can test it at this endpoint <a href="/api/echo">/api/echo</a></li>
            <li>You can view the docs at <a href="/swagger">/swagger</a></li>
        </ul>
    </p>
    </body>
    </html>'''
    return response.html(html)


root_api = Blueprint('Root API')


class EchoResponse:
    form = doc.Dictionary()
    headers = doc.Dictionary()
    json = doc.String()
    method = doc.String()


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


ROUTES_ATTACHED = False


def attach_routes(app):
    """
    Attach all module routes to the provided app.
    """
    global ROUTES_ATTACHED
    if ROUTES_ATTACHED:
        return
    ROUTES_ATTACHED = True
    # module.api_bp can be a Blueprint or BlueprintGroup
    blueprints = [module.api_bp for module in MODULES.values()]
    api_group = Blueprint.group(*blueprints, root_api, url_prefix='/api')
    app.blueprint(api_group)


def run_webserver(host: str, port: int, workers: int = 8):
    attach_routes(api_app)
    set_sanic_url_parts(host, port)
    # Enable debugging output
    debug = logger.level <= logging.DEBUG
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


if __name__ == '__main__':
    # If run directly, we'll make our own parser
    p = argparse.ArgumentParser()
    init_parser(p)
    main(p.parse_args())
