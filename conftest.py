# Import conftest for test fixtures
import os

from wrolpi.conftest import *  # noqa

os.environ['DB_PORT'] = '54321'
