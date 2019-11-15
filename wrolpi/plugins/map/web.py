"""
These are the UI classes for your plugin.  They should all return a rendered HTML template from Jinja2.  These methods
should NEVER make changes to the DB, do that in your API methods.

Required: PLUGIN_ROOT, PLUGINS, set_plugins, ClientRoot
"""
from dictorm import DictDB
from sanic import Blueprint, response
from sanic.request import Request

from wrolpi.common import env

PLUGIN_ROOT = 'map'
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


client_bp = Blueprint('content_map', url_prefix='/map')


@client_bp.get('/')
def index(request: Request):
    template = env.get_template('wrolpi/plugins/map/templates/instructions.html')
    kwargs = _get_render_kwargs()
    html = template.render(**kwargs)
    return response.html(html)
