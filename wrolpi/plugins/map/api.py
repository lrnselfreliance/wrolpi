"""
These are the API methods for your plugin.  It will be accessed through the key you set in user_plugins.py.  These
should return JSON, if anything.  These will be required to be accessed through a cherrypy.dispatch.MethodDispatcher(),
which means the request will be routed by the HTTP method you use.  For example, the video plugin:

    PUT /api/videos/settings

    will be routed to videos.api.APIRoot.settings.PUT


Required: APIRoot
"""

import cherrypy
from dictorm import DictDB

from wrolpi.tools import setup_tools

setup_tools()


# Do not change the name of this class, it is expected by wrolpi.web
class APIRoot(object):

    def __init__(self):
        self.pbf = PBFApi()


@cherrypy.expose
class PBFApi(object):

    @cherrypy.tools.db()
    def POST(self, db: DictDB, **form_data):
        print(form_data)
        pbf_url = form_data.get('pbf_url')
        # TODO call wget --continue on pbf_url, save with unique name so many pbfs can be downloaded
