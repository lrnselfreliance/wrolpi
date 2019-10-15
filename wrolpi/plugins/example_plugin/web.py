"""
These are the UI classes for your plugin.  They should all return a rendered HTML template from Jinja2.  These methods
should NEVER make changes to the DB, do that in your API methods.

Required: LINK, PLUGINS, set_plugins, ClientRoot
"""
import cherrypy
from dictorm import DictDB

from wrolpi.common import env
from wrolpi.plugins.example_plugin.common import hello

# This is your link suffix.  It will be used to link to your web classes here.
LINK = 'example_plugin'

# This will be set once all plugins are loaded
PLUGINS = None


def set_plugins(plugins):
    global PLUGINS
    PLUGINS = plugins


class ClientRoot(object):

    @cherrypy.expose
    @cherrypy.tools.db()
    def index(self, db: DictDB):
        # curl http://127.0.0.1:8080/example_plugin
        template = env.get_template('wrolpi/plugins/example_plugin/templates/index.html')
        html = template.render(hello=hello(), plugins=PLUGINS)
        return html
