#! /usr/bin/env python3
"""
This file is a simple Python/Sanic wrapper around the single-file CLI command.
"""
import base64
import json
import logging
import subprocess
import tempfile

from sanic import Sanic, response
from sanic.request import Request

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

app = Sanic('archive')

index_html = '''
<html>
<body>
<h2>This is the WROLPi archiving service.</h2>
<p>
    This is not meant to be used directly, it should be called by the
    archive module.
<p>
</body>
</html>
'''


@app.get('/')
async def index(_):
    return response.html(index_html)


async def call_single_file(url) -> bytes:
    """
    Call the CLI command for SingleFile.

    See https://github.com/gildas-lormeau/SingleFile
    """
    logger.info(f'archiving {url}')
    cmd = ['/usr/src/app/node_modules/single-file/cli/single-file', url,
           '--browser-executable-path', '/usr/bin/chromium-browser', '--browser-args', '["--no-sandbox"]',
           '--dump-content']
    output = subprocess.check_output(cmd)
    logger.debug(f'done archiving {url}')
    return output


async def extract_readability(path: str, url: str) -> dict:
    """
    Call the CLI command for readability-extractor.

    See https://github.com/ArchiveBox/readability-extractor
    """
    logger.info(f'readability for {url}')
    cmd = ['readability-extractor', path, url]
    output = subprocess.check_output(cmd)
    output = json.loads(output)
    logger.debug(f'done readability for {url}')
    return output


async def take_screenshot(url: str) -> bytes:
    cmd = ['/usr/bin/chromium-browser', '--headless', '--disable-gpu', '--no-sandbox', '--screenshot',
           '--window-size=1920,1080', url]
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            subprocess.check_output(cmd, cwd=tmp_dir)
        except Exception as e:
            logger.error(f'Failed to screenshot {url}', exc_info=True)
            return b''

        try:
            with open(f'{tmp_dir}/screenshot.png', 'rb') as fh:
                png = fh.read()
                return base64.b64encode(png)
        except FileNotFoundError:
            return b''


@app.post('/json')
async def post_archive(request: Request):
    url = request.json['url']
    singlefile = await call_single_file(url)
    screenshot = await take_screenshot(url)
    with tempfile.NamedTemporaryFile('wb') as fh:
        fh.write(singlefile)
        readability = await extract_readability(fh.name, url)

    ret = dict(
        url=url,
        singlefile=singlefile.decode(),
        readability=readability,
        screenshot=screenshot.decode(),
    )
    return response.json(ret)


if __name__ == '__main__':
    app.run('0.0.0.0', 8080, workers=4, auto_reload=True)
