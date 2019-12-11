import argparse
import pathlib
from functools import wraps

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
def teardown_db_context(request, response):
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


def attach_routes(app):
    """
    Attach all module routes to the provided app.
    """
    # routes: /api/*
    blueprints = [i.api_bp for i in MODULES.values()]
    api_group = Blueprint.group(*blueprints, root_api, url_prefix='/api')
    app.blueprint(api_group)


def run_webserver(host: str, port: int, workers: int = 8):
    attach_routes(api_app)
    set_sanic_url_parts(host, port)
    api_app.run(host, port, workers=workers)


def init_parser(parser):
    # Called by WROLPI's main() function
    parser.add_argument('-H', '--host', default='127.0.0.1', help='What network interface to connect webserver')
    parser.add_argument('-p', '--port', default=8080, type=int, help='What port to connect webserver')
    parser.add_argument('-w', '--workers', default=4, type=int, help='How many web workers to run')


def main(args):
    run_webserver(args.host, args.port, args.workers)
    return 0


if __name__ == '__main__':
    # If run directly, we'll make our own parser
    parser = argparse.ArgumentParser()
    init_parser(parser)
    main(parser.parse_args())
