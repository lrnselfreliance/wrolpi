import contextlib
import email.utils
import functools
import http.server
import json
import os
import pathlib
import tempfile
import threading
from typing import Callable

import pytest

from wrolpi.common import set_test_media_directory
from wrolpi.sync.config import get_sync_config


class CaddyLikeHandler(http.server.SimpleHTTPRequestHandler):
    """Serves a directory at /media/ the way the primary's Caddy does: Range requests, and JSON directory listings
    when asked with `Accept: application/json`."""

    def __init__(self, *args, server_state: dict, **kwargs):
        self.server_state = server_state
        super().__init__(*args, **kwargs)

    def log_message(self, *args):
        pass

    def translate_path(self, path):
        path = path.split('?', 1)[0]
        if path.startswith('/media/'):
            return super().translate_path(path[len('/media'):])
        return '/nonexistent-wrolpi-sync-test-path'

    def do_GET(self):
        self.server_state['requests'].append((self.path, self.headers.get('Range')))
        path = self.translate_path(self.path)
        if os.path.isdir(path) and 'application/json' in (self.headers.get('Accept') or ''):
            entries = list()
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                is_dir = os.path.isdir(full)
                entries.append(dict(name=name + ('/' if is_dir else ''), size=os.path.getsize(full), is_dir=is_dir,
                                    mod_time=email.utils.formatdate(os.path.getmtime(full))))
            body = json.dumps(entries).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.server_state['omit_length'] and os.path.isfile(path):
            # The body ends when the connection closes (HTTP/1.0), so the client cannot know its size.
            self.send_response(200)
            self.end_headers()
            with open(path, 'rb') as fh:
                self.wfile.write(fh.read())
            return

        range_ = self.headers.get('Range')
        if range_ and self.server_state['honor_range'] and os.path.isfile(path):
            start = int(range_.split('=', 1)[1].split('-', 1)[0])
            size = os.path.getsize(path)
            if start >= size:
                self.send_response(416)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            self.send_response(206)
            self.send_header('Content-Length', str(size - start))
            self.send_header('Content-Range', f'bytes {start}-{size - 1}/{size}')
            self.end_headers()
            with open(path, 'rb') as fh:
                fh.seek(start)
                self.wfile.write(fh.read())
            return

        super().do_GET()


@pytest.fixture
def primary_media_server() -> Callable[[pathlib.Path], tuple]:
    """Start a server that serves a directory like the primary's Caddy.  Returns (url, state); `state['requests']`
    records (path, Range header) of each request, `state['honor_range'] = False` makes it ignore Range, and
    `state['omit_length'] = True` makes it send files without a Content-Length."""
    servers = list()

    def start(directory: pathlib.Path):
        state = dict(requests=list(), honor_range=True, omit_length=False)
        handler = functools.partial(CaddyLikeHandler, directory=str(directory), server_state=state)
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f'http://127.0.0.1:{server.server_address[1]}', state

    yield start

    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture
def secondary_directory(test_directory) -> pathlib.Path:
    """A second, empty media directory.  The test switches to it (`use_secondary`) after preparing the primary in
    `test_directory`; both "machines" share the test database."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = pathlib.Path(tmp_dir).resolve()
        (path / 'config').mkdir()
        try:
            yield path
        finally:
            set_test_media_directory(test_directory)


@pytest.fixture
def make_secondary(test_wrolpi_config):
    """Make this WROLPi a secondary of `url`."""

    def make(url: str = 'http://127.0.0.1:1'):
        get_sync_config()._config.update(role='secondary', primary_url=url)

    return make


@contextlib.contextmanager
def media_directory(path: pathlib.Path):
    set_test_media_directory(path)
    yield path
