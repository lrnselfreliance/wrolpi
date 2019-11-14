import subprocess
from pathlib import Path
from urllib.parse import urlparse

from sanic import Blueprint

client_bp = Blueprint('content_map', url_prefix='/map')


@client_bp.route('/pbf', methods=['POST'])
def pbf_post(self, **form_data):
    pbf_url = form_data.get('pbf_url')
    parsed = urlparse(pbf_url)
    if not parsed.scheme or not parsed.netloc or not parsed.path:
        raise Exception('Invalid PBF url')

    put_async_download(pbf_url)


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
