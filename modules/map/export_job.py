"""Making the PDF of an exported map as a Job.

A PDF of a map is a minute or two of work on a Raspberry Pi: too long for a request to wait on.  So the browser
describes the map and is given the id of an export; it sends the image of each layer, one a request (together they
are a hundred megabytes, more than one request may be); then it asks for the PDF to be made, and is given the id of
a Job (see `wrolpi.jobs`).  It watches the Job, and when the Job is done it fetches the PDF.

An export is a directory, which holds what was said of the map, the images until the PDF is made of them, and then
the PDF.  It is on a disk, not in memory, and is removed when it is old.
"""
import asyncio
import json
import pathlib
import re
import shutil
import time
import uuid
from typing import List, Optional

from modules.map import export
from wrolpi.common import logger
from wrolpi.jobs import COMPLETE, get_current_job, get_job, register_job

logger = logger.getChild(__name__)

__all__ = ['ExportNotFound', 'ExportNotReady', 'create_export', 'save_layer', 'start_export', 'get_export_pdf',
           'remove_old_exports', 'map_export_pdf_job', 'EXPORT_ROOT', 'EXPORT_KEEP_SECONDS', 'MAX_LAYER_BYTES']

# Where exports are kept.  Not /tmp, which is memory on a Raspberry Pi.
EXPORT_ROOT = pathlib.Path('/var/tmp/wrolpi-map-export')
# An export which is this old is removed: its PDF was fetched long ago, or never will be.
EXPORT_KEEP_SECONDS = 60 * 60
# The most one image of a layer may be.  A layer of a quadrangle at 400 DPI is 20 to 30 MB as a PNG.
MAX_LAYER_BYTES = 64 * 1024 * 1024
JOB_NAME = 'map_export_pdf'
META_FILE = 'meta.json'
PDF_FILE = 'map.pdf'
EXPORT_ID = re.compile(r'^[0-9a-f]{32}$')
PNG_MAGIC, JPEG_MAGIC = b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff'


class ExportNotFound(Exception):
    """There is no such export: it was never made, or it was old and has been removed."""


class ExportNotReady(Exception):
    """The export is not as far along as it was asked to be."""


class ExportCancelled(Exception):
    """The Job which was making the PDF was cancelled."""


def _directory(export_id: str) -> pathlib.Path:
    """Where an export is.  The id is what `create_export` gave, and nothing else: it becomes part of a path."""
    if not EXPORT_ID.match(str(export_id)):
        raise ExportNotFound(f'There is no export {export_id!r}')
    directory = EXPORT_ROOT / export_id
    if not (directory / META_FILE).is_file():
        raise ExportNotFound(f'There is no export {export_id!r}')
    return directory


def _read_meta(directory: pathlib.Path) -> dict:
    return json.loads((directory / META_FILE).read_text())


def _write_meta(directory: pathlib.Path, meta: dict):
    (directory / META_FILE).write_text(json.dumps(meta))


def _layer_file(directory: pathlib.Path, index: int) -> pathlib.Path:
    return directory / f'layer-{index:03d}'


def remove_old_exports(now: float = None):
    """Remove the exports which are old.  An export is a hundred megabytes until its PDF is made, and tens after."""
    now = time.time() if now is None else now
    if not EXPORT_ROOT.is_dir():
        return
    for directory in EXPORT_ROOT.iterdir():
        try:
            if directory.is_dir() and now - directory.stat().st_mtime > EXPORT_KEEP_SECONDS:
                shutil.rmtree(directory, ignore_errors=True)
        except OSError as e:
            logger.warning(f'Could not remove the old map export {directory}', exc_info=e)


def create_export(layers: List[str], width: int, height: int, dpi: float, title: Optional[str] = None,
                  bounds=None, sheet: Optional[export.Sheet] = None) -> str:
    """Begin an export of a map of these layers (their names, from the bottom up).  Returns its id.

    @raise InvalidExport: When such a map can not be exported; no image has been sent yet."""
    bounds = export.check_export(len(layers), width, height, dpi, bounds, sheet)
    remove_old_exports()
    export_id = uuid.uuid4().hex
    directory = EXPORT_ROOT / export_id
    directory.mkdir(parents=True)
    _write_meta(directory, dict(
        layers=[str(i) for i in layers], width=width, height=height, dpi=dpi, title=title, bounds=bounds,
        sheet=dict(name=sheet.name, credits=list(sheet.credits), date=sheet.date) if sheet else None,
        job_id=None,
    ))
    return export_id


def save_layer(export_id: str, index: int, image: bytes):
    """Keep the image of one layer of an export.

    @raise InvalidExport: When it is not an image of a layer of that export."""
    directory = _directory(export_id)
    meta = _read_meta(directory)
    if meta['job_id']:
        raise export.InvalidExport('The PDF of this map is already being made')
    if not 0 <= index < len(meta['layers']):
        raise export.InvalidExport(f'The map has {len(meta["layers"])} layers; there is no layer {index}')
    if not image or len(image) > MAX_LAYER_BYTES:
        raise export.InvalidExport(f'The image of the layer {meta["layers"][index]!r} is empty, or is too large')
    if not image.startswith((PNG_MAGIC, JPEG_MAGIC)):
        raise export.InvalidExport(f'The layer {meta["layers"][index]!r} is not a PNG or JPEG image')
    _layer_file(directory, index).write_bytes(image)


def start_export(export_id: str) -> str:
    """Queue the Job which makes the PDF of an export, all of whose images have been sent.  Returns the Job's id;
    asked again, the same Job's."""
    directory = _directory(export_id)
    meta = _read_meta(directory)
    if meta['job_id']:
        return meta['job_id']
    missing = [name for index, name in enumerate(meta['layers']) if not _layer_file(directory, index).is_file()]
    if missing:
        raise ExportNotReady(f'The images of {len(missing)} layers have not been sent: {", ".join(missing[:5])}')
    job_id = map_export_pdf_job.enqueue(description=f'Map PDF: {meta["title"] or "a map"}', export_id=export_id)
    meta['job_id'] = job_id
    _write_meta(directory, meta)
    return job_id


def get_export_pdf(export_id: str) -> pathlib.Path:
    """The PDF of an export.

    @raise ExportNotReady: When it has not been made (yet, or because the Job failed or was cancelled)."""
    directory = _directory(export_id)
    pdf = directory / PDF_FILE
    if not pdf.is_file():
        job_id = _read_meta(directory).get('job_id')
        status = get_job(job_id)['status'] if job_id else 'not started'
        raise ExportNotReady(f'The PDF has not been made (the job is {status})' if status != COMPLETE
                             else 'The PDF is gone')
    return pdf


def _make_pdf(directory: pathlib.Path, job) -> dict:
    """Make the PDF of an export from its images, which are removed whether or not it could be made."""
    meta = _read_meta(directory)
    layers = [export.ExportLayer(name=name, path=_layer_file(directory, index))
              for index, name in enumerate(meta['layers'])]
    sheet = export.Sheet(**meta['sheet']) if meta['sheet'] else None

    def progress(done: int, steps: int):
        # Between two layers is where the work can be stopped.
        if job.cancel_requested():
            raise ExportCancelled()
        job.set_progress(100 * done / steps)

    try:
        pdf = export.build_layered_pdf(layers, meta['width'], meta['height'], meta['dpi'], meta['title'],
                                       meta['bounds'], sheet, progress=progress)
        # Under another name until all of it is written: a PDF which is there is a whole one.
        partial = directory / f'{PDF_FILE}.part'
        partial.write_bytes(pdf)
        partial.rename(directory / PDF_FILE)
        return dict(export_id=directory.name, size=len(pdf))
    finally:
        for layer in layers:
            layer.path.unlink(missing_ok=True)


@register_job(JOB_NAME)
async def map_export_pdf_job(export_id: str):
    """Make the PDF of an export.  The work is in a thread: this process has other things to keep doing."""
    directory = _directory(export_id)
    job = get_current_job()
    job.log(f'Making the PDF of the map export {export_id}')
    try:
        result = await asyncio.to_thread(_make_pdf, directory, job)
    except ExportCancelled:
        # The work saw that the Job was cancelled before the Job's runner did.  The runner is who ends a cancelled
        # Job (it looks every second), so wait for it to.
        await asyncio.Event().wait()
        raise
    job.log(f'The PDF is {result["size"]} bytes')
    return result
