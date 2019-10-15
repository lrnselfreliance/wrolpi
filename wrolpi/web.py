import argparse
import pathlib

import cherrypy

from wrolpi.api import API, API_CONFIG
from wrolpi.common import env
from wrolpi.user_plugins import PLUGINS

cwd = pathlib.Path(__file__).parent
static_dir = (cwd / 'static').absolute()

ROOT_CONFIG = {
    '/static': {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': str(static_dir),
    },
}


class ClientRoot(object):

    def __init__(self):
        # Install plugins defined in user_plugins
        for name, plugin in PLUGINS.items():
            setattr(self, name, plugin.ClientRoot())

    @cherrypy.expose
    def index(self):
        template = env.get_template('wrolpi/templates/index.html')
        return template.render(plugins=PLUGINS)

    @cherrypy.expose
    def settings(self):
        template = env.get_template('wrolpi/templates/settings.html')
        return template.render(plugins=PLUGINS)


def start_webserver(host, port):
    cherrypy.config.update({
        'server.socket_host': host,
        'server.socket_port': port,
    })

    cherrypy.tree.mount(ClientRoot(), '/', config=ROOT_CONFIG)
    cherrypy.tree.mount(API(), '/api', config=API_CONFIG)

    cherrypy.engine.start()
    cherrypy.engine.block()


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
