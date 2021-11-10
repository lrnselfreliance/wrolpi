#! /usr/bin/env python3
"""
This file is a simple Python/Sanic wrapper around the single-file CLI command.
"""
import asyncio
import base64
import gzip
import json
import logging
import os.path
import pathlib
import subprocess
import tempfile

from sanic import Sanic, response
from sanic.request import Request

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

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
    logger.debug(f'archive cmd: {cmd}')
    output = subprocess.check_output(cmd)
    logger.debug(f'done archiving for {url}')
    return output


async def extract_readability(path: str, url: str) -> dict:
    """
    Call the CLI command for readability-extractor.

    See https://github.com/ArchiveBox/readability-extractor
    """
    logger.info(f'readability for {url}')
    cmd = ['readability-extractor', path, url]
    logger.debug(f'readability cmd: {cmd}')
    output = subprocess.check_output(cmd)
    output = json.loads(output)
    logger.debug(f'done readability for {url}')
    return output


async def take_screenshot(url: str) -> bytes:
    cmd = ['/usr/bin/chromium-browser', '--headless', '--disable-gpu', '--no-sandbox', '--screenshot',
           '--window-size=1280,720', url]
    logger.info(f'Screenshot: {url}')
    logger.debug(f'Screenshot cmd: {cmd}')
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            subprocess.check_output(cmd, cwd=tmp_dir)
        except Exception:
            logger.error(f'Failed to screenshot {url}', exc_info=True)
            return b''

        path = pathlib.Path(f'{tmp_dir}/screenshot.png')
        if not path.is_file():
            return b''

        size = os.path.getsize(path)
        logger.info(f'Successful screenshot ({size} bytes) at {path}')
        png = path.read_bytes()
        return png


def prepare_bytes(b: bytes) -> str:
    """
    Compress and encode bytes for smaller response.
    """
    b = gzip.compress(b)
    b = base64.b64encode(b)
    b = b.decode()
    return b


@app.post('/json')
async def post_archive(request: Request):
    url = request.json['url']
    try:
        singlefile, screenshot = await asyncio.gather(call_single_file(url), take_screenshot(url))
        with tempfile.NamedTemporaryFile('wb') as fh:
            fh.write(singlefile)
            readability = await extract_readability(fh.name, url)

        # Compress for smaller response.
        singlefile = prepare_bytes(singlefile)
        screenshot = prepare_bytes(screenshot)

        ret = dict(
            url=url,
            singlefile=singlefile,
            readability=readability,
            screenshot=screenshot,
        )
        return response.json(ret)
    except Exception:
        logger.fatal(f'Failed to archive {url}', exc_info=True)
        return response.json({'error': f'Failed to archive {url}'})


if __name__ == '__main__':
    app.run('0.0.0.0', 8080, workers=4)
