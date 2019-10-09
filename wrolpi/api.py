import cherrypy

from wrolpi.user_plugins import PLUGINS

API_CONFIG = {
    '/': {
        'tools.trailing_slash.on': False,
        'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
    },
}


@cherrypy.expose
class API(object):

    def __init__(self):
        for name, plugin in PLUGINS.items():
            setattr(self, name, plugin.APIRoot())
