import threading

import cherrypy

from wrolpi.common import get_db, setup_relationships


class DBTool(cherrypy.Tool):
    """Setup and attach a DB to a request before the handler gets it.  Teardown the DB after
    a request."""

    def __init__(self):
        self.db_conn = None
        self.db = None
        self.thread_id = None
        cherrypy.Tool.__init__(self, 'before_handler', self.setup_db, priority=25)

    def setup_db(self):
        self.thread_id = threading.get_ident()
        self.db_conn, self.db = get_db()
        req = cherrypy.request
        req.params['db'] = self.db

    def _setup(self):
        cherrypy.Tool._setup(self)
        cherrypy.request.hooks.attach('on_end_request', self.teardown_db, priority=25)

    def teardown_db(self):
        self.db_conn.close()


TOOLS_ONCE = False


def setup_tools():
    global TOOLS_ONCE
    if TOOLS_ONCE:
        return
    TOOLS_ONCE = True
    cherrypy.tools.db = DBTool()
