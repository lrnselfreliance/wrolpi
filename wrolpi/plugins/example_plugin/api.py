"""
These are the API methods for your plugin.  It will be accessed through the key you set in user_plugins.py.  These
should return JSON, if anything.  These will be required to be accessed through a cherrypy.dispatch.MethodDispatcher(),
which means the request will be routed by the HTTP method you use.  For example, the video plugin:

    PUT /api/videos/settings

    will be routed to videos.api.APIRoot.settings.PUT


Required: APIRoot
"""
import json

import cherrypy
from dictorm import DictDB

from wrolpi.plugins.example_plugin.common import hello


# Do not change the name of this class, it is expected by wrolpi.web
class APIRoot(object):

    def __init__(self):
        self.settings = SettingsAPI()


@cherrypy.expose
class SettingsAPI(object):

    @cherrypy.tools.db()
    def GET(self, db: DictDB):
        # curl http://127.0.0.1:8080/api/example_plugin/settings
        return json.dumps({'hello': hello()})

    @cherrypy.tools.db()
    def POST(self, db: DictDB, **form_data):
        # curl -X POST -d arg=val http://127.0.0.1:8080/api/example_plugin/settings
        with db.transaction(commit=True):
            return json.dumps({'hello': hello(), 'form_data': form_data})
