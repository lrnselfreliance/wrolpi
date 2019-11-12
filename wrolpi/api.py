import cherrypy
from sanic import Blueprint

from wrolpi.user_plugins import PLUGINS

API_CONFIG = {
    '/': {
        'tools.trailing_slash.on': False,
        'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
    },
}

root_api_bp = Blueprint('root_api')
blueprints = [i.api_bp for i in PLUGINS.values()]
api_group = root_api_bp.group(*blueprints, url_prefix='/api')
