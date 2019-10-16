"""
These are the UI classes for your plugin.  They should all return a rendered HTML template from Jinja2.  These methods
should NEVER make changes to the DB, do that in your API methods.

Required: PLUGIN_ROOT, PLUGINS, set_plugins, ClientRoot
"""
import cherrypy
from dictorm import DictDB

from wrolpi.common import env
from wrolpi.plugins.example_plugin.common import hello

# This is your link suffix.  It will be used to link to your web classes here.
PLUGIN_ROOT = 'example_plugin'
# Your plugin can be hidden on the navbar
HIDDEN = False

# This will be set once all plugins are loaded
PLUGINS = None


def set_plugins(plugins):
    global PLUGINS
    PLUGINS = plugins


def _get_render_kwargs(**kwargs):
    """
    This is a helper function (which you can delete if you want) which saves you from passing PLUGINS/etc every time.
    It will always include the default kwargs your template will require, as well as anything you pass to it.
    """
    d = dict()
    d['PLUGINS'] = PLUGINS
    d['PLUGIN_ROOT'] = PLUGIN_ROOT
    d.update(kwargs)
    return d


class ClientRoot(object):

    @cherrypy.expose
    @cherrypy.tools.db()
    def index(self, db: DictDB):
        # curl http://127.0.0.1:8080/example_plugin
        template = env.get_template('wrolpi/plugins/example_plugin/templates/index.html')
        kwargs = _get_render_kwargs(hello=hello())
        html = template.render(**kwargs)
        return html
