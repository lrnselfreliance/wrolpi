import subprocess
from pathlib import Path
from urllib.parse import urlparse

import cherrypy

from wrolpi.plugins.map.common import get_downloads, save_downloads
from wrolpi.tools import setup_tools

setup_tools()


class APIRoot(object):

    def __init__(self):
        self.pbf = PBFApi()


@cherrypy.expose
class PBFApi(object):

    def POST(self, **form_data):
        pbf_url = form_data.get('pbf_url')
        parsed = urlparse(pbf_url)
        if not parsed.scheme or not parsed.netloc or not parsed.path:
            raise Exception('Invalid PBF url')

        downloads = get_downloads()
        downloads = add_pbf_url_to_config(pbf_url, downloads)
        save_downloads(downloads)

        # TODO start downloads from file.  Do it asynchronously and without conflict


def get_http_file_size(url):
    proc = subprocess.run(['/usr/bin/wget', '--spider', '--timeout=10', url], stdin=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    stderr = proc.stderr
    for line in stderr.split(b'\n'):
        if line.startswith(b'Length:'):
            line = line.decode()
            size = line.partition('Length: ')[2].split(' ')[0]
            return size
    else:
        raise Exception(f'Unable to get length of {url}')


def add_pbf_url_to_config(pbf_url, config):
    size = get_http_file_size(pbf_url)
    parsed = urlparse(pbf_url)
    name = Path(parsed.path).name
    d = {pbf_url: {'size': size, 'destination': f'/tmp/{name}'}}
    try:
        config['pbf_urls'].update(d)
    except TypeError:
        config['pbf_urls'] = d
    return config


def async_download_file(url, destination):
    pass
