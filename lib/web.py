import argparse
import pathlib
from functools import wraps

from sanic import Blueprint, Sanic, response
from sanic.request import Request
from sanic_cors import CORS

from lib.common import env, logger
from lib.db import get_db
from lib.user_plugins import PLUGINS
from lib.vars import STATIC_DIR

cwd = pathlib.Path(__file__).parent

webapp = Sanic()
CORS(webapp)


# Add DB middleware
@webapp.middleware('request')
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


@webapp.middleware('response')
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


root_client = Blueprint('root')


@root_client.route('/')
async def index(request):
    template = env.get_template('templates/index.html')
    html = template.render(PLUGINS=PLUGINS)
    return response.html(html)


@root_client.route('/settings')
async def settings(request):
    template = env.get_template('templates/settings.html')
    html = template.render(PLUGINS=PLUGINS)
    return response.html(html)


root_api = Blueprint('echo_api_bp')


@root_api.route('/echo', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
async def echo(request: Request):
    return response.json({'request_json': request.json, 'method': request.method})


@root_api.route('/plugins')
async def plugins(request: Request):
    """Create a list of plugin links for the frontend.

    Example:
        [
            ('/videos', 'Videos'),
            ('/map', 'Map'),
        ]
    """
    request_plugins = [('/' + i.PLUGIN_ROOT, i.PRETTY_NAME) for i in PLUGINS.values()]
    return response.json(request_plugins)


def attach_routes(app):
    """
    Attach all default and plugin routes to the provided app.
    """
    # routes: /static/*
    app.static('/static', str(STATIC_DIR))

    # routes: /*
    client_bps = [i.client_bp for i in PLUGINS.values()]
    client_group = Blueprint.group(client_bps, root_client)
    app.blueprint(client_group)

    # routes: /api/*
    blueprints = [i.api_bp for i in PLUGINS.values()]
    api_group = Blueprint.group(*blueprints, root_api, url_prefix='/api')
    app.blueprint(api_group)


def run_webserver(host: str, port: int):
    attach_routes(webapp)
    webapp.run(host, port, workers=4)


def init_parser(parser):
    # Called by WROLPI's main() function
    parser.add_argument('-H', '--host', default='127.0.0.1', help='What network interface to connect webserver')
    parser.add_argument('-p', '--port', default=8080, type=int, help='What port to connect webserver')


def main(args):
    run_webserver(args.host, args.port)
    return 0


if __name__ == '__main__':
    # If run directly, we'll make our own parser
    parser = argparse.ArgumentParser()
    init_parser(parser)
    main(parser.parse_args())
