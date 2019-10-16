import cherrypy

from wrolpi.common import get_db, logger


class DBTool(cherrypy.Tool):
    """Setup and attach a DB to a request before the handler gets it.  Teardown the DB after
    a request."""

    def __init__(self):
        self.pool = None
        self.conn = None
        self.db = None
        cherrypy.Tool.__init__(self, 'before_handler', self.setup_db, priority=25)

    def setup_db(self):
        self.pool, self.conn, self.db, self.key = get_db()
        req = cherrypy.request
        req.params['db'] = self.db

    def _setup(self):
        cherrypy.Tool._setup(self)
        cherrypy.request.hooks.attach('on_end_request', self.teardown_db, priority=25)

    def teardown_db(self):
        try:
            self.pool.putconn(self.conn, key=self.key, close=False)
        except KeyError:
            # connection with this key was already closed
            logger.debug('Failed to putconn, already closed?')
