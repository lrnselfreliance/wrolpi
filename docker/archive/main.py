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
import traceback
from json import JSONDecodeError

from sanic import Sanic, response
from sanic.request import Request

# Log using datetime and log level.  Log to stdout.
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

SINGLEFILE_PATH = pathlib.Path('/usr/src/app/node_modules/single-file-cli/single-file')
if not SINGLEFILE_PATH.is_file():
    SINGLEFILE_PATH = pathlib.Path('/usr/src/app/node_modules/single-file/cli/single-file')
if not SINGLEFILE_PATH.is_file():
    SINGLEFILE_PATH = pathlib.Path('/usr/src/.nvm/versions/node/v18.19.0/bin/single-file')
if not SINGLEFILE_PATH.is_file():
    raise FileNotFoundError("Can't find single-file executable!")

# Increase response timeout, archiving can take several minutes.
RESPONSE_TIMEOUT = 10 * 60
config = {
    'RESPONSE_TIMEOUT': RESPONSE_TIMEOUT,
}

app = Sanic('archive')
app.update_config(config)

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


async def check_output(cmd, always_log_stderr: bool = False, cwd=None, timeout: float = None):
    proc = None
    try:
        proc = await asyncio.create_subprocess_shell(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if always_log_stderr is True or proc.returncode != 0:
            # Always log when requested, or when the call failed.
            for line in stderr.decode().splitlines():
                logger.error(line)
        return stdout, stderr, proc.returncode
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()  # Wait for the process to fully terminate
        raise TimeoutError(f"Command '{cmd}' timed out after {timeout} seconds")


async def call_single_file(url) -> bytes:
    """
    Call the CLI command for SingleFile.

    See https://github.com/gildas-lormeau/SingleFile
    """
    logger.info(f'archiving {url}')
    cmd = f'{SINGLEFILE_PATH}' \
          r' --dump-content ' \
          f' "{url}"'
    logger.debug(f'archive cmd: {cmd}')
    stdout, stderr, return_code = await check_output(cmd, always_log_stderr=True, timeout=3 * 60)
    if return_code != 0 or not stdout:
        if stderr:
            for line in stderr.splitlines():
                logger.error(line.decode())
        raise RuntimeError(f'Failed to single-file {url} got the following error: {stderr}')
    logger.debug(f'done archiving for {url}')
    return stdout


async def extract_readability(path: str, url: str) -> dict:
    """
    Call the CLI command for readability-extractor.

    See https://github.com/ArchiveBox/readability-extractor
    """
    logger.info(f'readability for {url}')
    cmd = f'readability-extractor {path} "{url}"'
    logger.debug(f'readability cmd: {cmd}')
    stdout, stderr, return_code = await check_output(cmd, timeout=3 * 60)
    try:
        output = json.loads(stdout)
    except JSONDecodeError as e:
        stderr = stderr.decode() if stderr else None
        raise RuntimeError(f'Failed to extract readability.  {stderr}') from e
    logger.debug(f'done readability for {url}')
    return output


async def take_screenshot(url: str) -> bytes:
    cmd = '/usr/bin/google-chrome' \
          ' --headless' \
          ' --disable-gpu' \
          ' --no-sandbox' \
          ' --screenshot' \
          ' --window-size=1280x720' \
          f' "{url}"'
    logger.debug(f'Screenshot cmd: {cmd}')
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            stdout, stderr, return_code = await check_output(cmd, cwd=tmp_dir, timeout=1 * 60)
            if return_code != 0:
                raise ValueError(f'Screenshot failed {return_code=}')
        except Exception as e:
            logger.error(f'Failed to screenshot {url}', exc_info=e)
            return b''

        path = pathlib.Path(f'{tmp_dir}/screenshot.png')
        if not path.is_file():
            logger.warning(f'Screenshot command did not create screenshot of {url}')
            return b''

        size = os.path.getsize(path)
        logger.info(f'Successful screenshot of {url} ({size} bytes) at {path}')
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
        # May have been passed the singlefile contents, do the extractions and return.
        singlefile = request.json.get('singlefile')
        singlefile = base64.b64decode(singlefile) if singlefile else None

        # Use provided singlefile, or fetch and create from the internet.
        singlefile = singlefile or await call_single_file(url)

        # Use html suffix so chrome screenshot recognizes it as an HTML file.
        with tempfile.NamedTemporaryFile('wb', suffix='.html') as fh:
            fh.write(singlefile)
            fh.flush()
            readability = None
            try:
                readability = await extract_readability(fh.name, url)
            except Exception as e:
                # Readability had error, but its is not required.
                logger.error(f'Failed to get readability', exc_info=e)

            screenshot = None
            try:
                # Screenshot the local singlefile, if that fails try the URL.
                screenshot = await take_screenshot(f'file://{fh.name}')
            except Exception as e:
                logger.error(f'Failed to take screenshot of {fh.name}', exc_info=e)

            if not screenshot:
                logger.warning(f'Failed to screenshot local singlefile attempting to screenshot: {url}')
                try:
                    screenshot = await take_screenshot(url)
                except Exception as e:
                    logger.error(f'Failed to take screenshot of {url}', exc_info=e)

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
    except Exception as e:
        logger.error(f'Failed to archive {url}', exc_info=e)
        error = str(traceback.format_exc())
        return response.json({'error': f'Failed to archive {url} traceback is below... \n\n {error}'})


if __name__ == '__main__':
    app.run('0.0.0.0', 8080, workers=4, auto_reload=True)
