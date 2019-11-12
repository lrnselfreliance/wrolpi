import argparse
import pathlib

from sanic import Blueprint, Sanic, response

from wrolpi.tools import setup_tools

# Setup the tools before importing modules which rely on them
setup_tools()

from wrolpi.common import env
from wrolpi.user_plugins import PLUGINS
from wrolpi.api import api_group

cwd = pathlib.Path(__file__).parent
static_dir = (cwd / 'static').absolute()

ROOT_CONFIG = {
    '/static': {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': str(static_dir),
    },
}

root_client = Blueprint('root')


@root_client.route('/')
async def index(request):
    template = env.get_template('wrolpi/templates/index.html')
    html = template.render(PLUGINS=PLUGINS)
    return response.html(html)


@root_client.route('/settings')
async def settings(request):
    template = env.get_template('wrolpi/templates/settings.html')
    html = template.render(PLUGINS=PLUGINS)
    return response.html(html)


def start_webserver(host: str, port: int):
    app = Sanic()
    # /static/*
    app.static('/static', './wrolpi/static')

    # routes: /*
    client_bps = [i.client_bp for i in PLUGINS.values()]
    client_group = Blueprint.group(client_bps, root_client)
    # routes: /*/*
    app.blueprint(client_group)
    # routes: /api/*
    app.blueprint(api_group)

    app.run(host, port)


def init_parser(parser):
    # Called by WROLPI's main() function
    parser.add_argument('-H', '--host', default='127.0.0.1', help='What network interface to connect webserver')
    parser.add_argument('-p', '--port', default=8080, type=int, help='What port to connect webserver')


def main(args):
    start_webserver(args.host, args.port)
    return 0


if __name__ == '__main__':
    # If run directly, we'll make our own parser
    parser = argparse.ArgumentParser()
    init_parser(parser)
    args = parser.parse_args()
    main(args)
