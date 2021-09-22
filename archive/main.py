#! /usr/bin/env python3
"""
This file is a simple Python/Sanic wrapper around the single-file CLI command.
"""
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
<p>
    <h2>This is the WROLPi archiving service.</h2>
    This is not meant to be used directly, it should be called by the
    archive module.
</p>
<p>
    <form action='/html' method='post'>
        <input type='text' name='url'/>
        <button type='submit'>Get HTML</button>
    </form>
</p>
</body>
</html>
'''


@app.get('/')
async def index(_):
    return response.html(index_html)


async def call_single_file(url) -> bytes:
    logger.info(f'archiving {url}')
    cmd = ['/usr/src/app/node_modules/single-file/cli/single-file', url,
           '--browser-executable-path', '/usr/bin/chromium-browser', '--browser-args', '["--no-sandbox"]',
           '--dump-content']
    output = subprocess.check_output(cmd)
    logger.debug(f'done archiving {url}')
    return output


async def extract_readability(path: str, url: str) -> dict:
    logger.info(f'readability for {url}')
    cmd = ['readability-extractor', path, url]
    output = subprocess.check_output(cmd)
    output = json.loads(output)
    logger.debug(f'done readability for {url}')
    return output


@app.post('/html')
async def post_archive(request: Request):
    url = request.form['url'][0]
    singlefile = await call_single_file(url)
    return response.html(singlefile)


@app.post('/json')
async def post_archive(request: Request):
    url = request.json['url']
    singlefile = await call_single_file(url)
    with tempfile.NamedTemporaryFile('wb') as fh:
        fh.write(singlefile)
        readability = await extract_readability(fh.name, url)

    ret = dict(
        url=url,
        singlefile=singlefile.decode(),
        readability=readability,
    )
    return response.json(ret)


if __name__ == '__main__':
    app.run('0.0.0.0', 8080, workers=4, auto_reload=True)
