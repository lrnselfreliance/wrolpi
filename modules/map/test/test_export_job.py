import asyncio
import json
import os
import time

import pytest

from modules.map import export, export_job
from modules.map.test.test_export import make_image
from wrolpi import jobs

WIDTH, HEIGHT = 60, 90


def new_export(*names, **kwargs) -> str:
    return export_job.create_export(list(names), WIDTH, HEIGHT, 300, **kwargs)


def test_create_export(map_export_root):
    """An export is a directory which holds what was said of the map."""
    export_id = new_export('Background', 'Water', title='A quadrangle', bounds=[-150, 61.125, -149.875, 61.25],
                           sheet=export.Sheet(name='A quadrangle', credits=['Somebody'], date='2026-11-15'))
    assert export_job.EXPORT_ID.match(export_id)
    meta = json.loads((map_export_root / export_id / 'meta.json').read_text())
    assert meta['layers'] == ['Background', 'Water']
    assert meta['sheet'] == dict(name='A quadrangle', credits=['Somebody'], date='2026-11-15')
    assert meta['job_id'] is None

    # A map which can not be exported is not begun.
    with pytest.raises(export.InvalidExport, match='no layers'):
        new_export()
    with pytest.raises(export.InvalidExport, match='edges of the map are needed'):
        new_export('A', sheet=export.Sheet())
    assert len(list(map_export_root.iterdir())) == 1


@pytest.mark.parametrize('export_id', ['0' * 32, '', 'nothing', '../' + '0' * 29, '0' * 31 + '/', None])
def test_unknown_export(export_id, map_export_root):
    """An id which was not given by an export is of no export, whatever it would be as a path."""
    map_export_root.mkdir()
    (map_export_root.parent / 'meta.json').write_text('{}')
    with pytest.raises(export_job.ExportNotFound):
        export_job.save_layer(export_id, 0, make_image())
    with pytest.raises(export_job.ExportNotFound):
        export_job.get_export_pdf(export_id)


def test_remove_old_exports(map_export_root):
    """An export is removed when it is old; a new export is when that is looked for."""
    old, new = new_export('A'), new_export('A')
    export_job.save_layer(old, 0, make_image())
    hours_ago = time.time() - export_job.EXPORT_KEEP_SECONDS - 60
    os.utime(map_export_root / old, (hours_ago, hours_ago))
    (map_export_root / 'a file which is not an export').write_text('left alone')

    newest = new_export('A')
    assert sorted(i.name for i in map_export_root.iterdir() if i.is_dir()) == sorted([new, newest])
    assert (map_export_root / 'a file which is not an export').is_file()
    with pytest.raises(export_job.ExportNotFound):
        export_job.start_export(old)

    # Nothing to remove, and nowhere to look, are not errors.
    export_job.remove_old_exports()
    export_job.EXPORT_ROOT = map_export_root / 'not made yet'
    export_job.remove_old_exports()


@pytest.mark.asyncio
async def test_job_makes_the_pdf(async_client, map_export_root):
    """The Job makes the PDF from the images, says how far along it is, and removes the images."""
    export_id = new_export('Background', 'Water', title='A quadrangle')
    export_job.save_layer(export_id, 0, make_image())
    export_job.save_layer(export_id, 1, make_image((0, 0, 255, 255), image_format='JPEG'))
    directory = map_export_root / export_id
    assert sorted(i.name for i in directory.iterdir()) == ['layer-000', 'layer-001', 'meta.json']

    job_id = export_job.start_export(export_id)
    assert job_id.startswith('map_export_pdf-')
    job = await jobs.wait_for_job(job_id, timeout=60)
    assert job['status'] == 'complete', job
    assert job['progress'] == 100
    assert job['result']['export_id'] == export_id

    pdf = export_job.get_export_pdf(export_id)
    assert pdf.read_bytes().startswith(b'%PDF-')
    assert job['result']['size'] == pdf.stat().st_size
    # Only what was said of the map, and the PDF, are kept.
    assert sorted(i.name for i in directory.iterdir()) == ['map.pdf', 'meta.json']


@pytest.mark.asyncio
async def test_job_progress(async_client, map_export_root, monkeypatch):
    """The Job says how far along it is as each layer is looked at and then put in the PDF."""
    seen = []
    real_set_progress = jobs.JobContext.set_progress

    def set_progress(self, percent):
        seen.append(percent)
        real_set_progress(self, percent)

    monkeypatch.setattr(jobs.JobContext, 'set_progress', set_progress)
    export_id = new_export('A', 'B')
    for index in range(2):
        export_job.save_layer(export_id, index, make_image())
    await jobs.wait_for_job(export_job.start_export(export_id), timeout=60)
    assert seen == [0, 25, 50, 75, 100]


@pytest.mark.asyncio
async def test_job_fails(async_client, map_export_root):
    """A map which can not be made into a PDF fails the Job; its images are removed all the same."""
    export_id = new_export('A', 'B')
    export_job.save_layer(export_id, 0, make_image())
    export_job.save_layer(export_id, 1, make_image(size=(10, 10)))
    job = await jobs.wait_for_job(export_job.start_export(export_id), timeout=60)
    assert job['status'] == 'failed'
    assert '10x10' in job['error']
    assert sorted(i.name for i in (map_export_root / export_id).iterdir()) == ['meta.json']
    with pytest.raises(export_job.ExportNotReady, match='failed'):
        export_job.get_export_pdf(export_id)


@pytest.mark.asyncio
async def test_job_cancelled(async_client, map_export_root, monkeypatch):
    """A cancelled Job stops between two layers, makes no PDF, and removes the images."""
    export_id = new_export('A', 'B', 'C')
    for index in range(3):
        export_job.save_layer(export_id, index, make_image())
    job_id = export_job.start_export(export_id)

    # The Job is cancelled while its first layer is looked at.
    real_check = export._check_layer
    checked = []

    def check_layer(layer, width, height):
        checked.append(layer.name)
        # As `cancel_job` asks a running Job to stop.  (Not `cancel_job` itself: it logs while it holds the Jobs'
        # lock, and what is logged inside a Job is written to the Job, which takes that lock.)
        jobs._update_job(job_id, cancel_requested=True)
        return real_check(layer, width, height)

    monkeypatch.setattr(export, '_check_layer', check_layer)
    job = await jobs.wait_for_job(job_id, timeout=60)
    assert job['status'] == 'cancelled'
    # The work is in a thread, which stops when it next looks.
    for _ in range(100):
        if not any(i.name.startswith('layer-') for i in (map_export_root / export_id).iterdir()):
            break
        await asyncio.sleep(0.05)
    assert checked == ['A']
    assert sorted(i.name for i in (map_export_root / export_id).iterdir()) == ['meta.json']
    with pytest.raises(export_job.ExportNotReady, match='cancelled'):
        export_job.get_export_pdf(export_id)


def test_layers_are_read_one_at_a_time(tmp_path):
    """A layer in a file is read when it is needed, not when the map is described."""
    path = tmp_path / 'layer'
    layer = export.ExportLayer('A', path=path)
    path.write_bytes(make_image())
    assert layer.read() == make_image()
    assert export.ExportLayer('A', image=b'given').read() == b'given'
    pdf = export.build_layered_pdf([layer], WIDTH, HEIGHT, 300)
    assert pdf.startswith(b'%PDF-')


def test_progress_may_stop_the_work():
    """What is told how far along the PDF is may stop it."""
    calls = []

    def progress(done, steps):
        calls.append((done, steps))
        if done == 3:
            raise RuntimeError('enough')

    layers = [export.ExportLayer(str(i), make_image()) for i in range(3)]
    with pytest.raises(RuntimeError, match='enough'):
        export.build_layered_pdf(layers, WIDTH, HEIGHT, 300, progress=progress)
    assert calls == [(0, 6), (1, 6), (2, 6), (3, 6)]
