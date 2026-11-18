import asyncio
import json
import os
import stat
import threading
import time
from http import HTTPStatus

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
    assert meta['sheet'] == dict(name='A quadrangle', credits=['Somebody'], date='2026-11-15',
                                 contour_interval=None, contour_unit=None, legend=None)
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


def age(directory, seconds=export_job.EXPORT_KEEP_SECONDS + 60):
    """Make an export look as old as that."""
    then = time.time() - seconds
    os.utime(directory, (then, then))


def test_remove_old_exports(map_export_root, monkeypatch):
    """An export is removed when it is old; a new export is when that is looked for."""
    old, new = new_export('A'), new_export('A')
    export_job.save_layer(old, 0, make_image())
    age(map_export_root / old)
    (map_export_root / 'a file which is not an export').write_text('left alone')

    newest = new_export('A')
    assert sorted(i.name for i in map_export_root.iterdir() if i.is_dir()) == sorted([new, newest])
    assert (map_export_root / 'a file which is not an export').is_file()
    with pytest.raises(export_job.ExportNotFound):
        export_job.start_export(old)

    # Nothing to remove, and nowhere to look, are not errors; and looking does not make the directory.
    export_job.remove_old_exports()
    monkeypatch.setattr(export_job, 'EXPORT_ROOT', map_export_root / 'not made yet')
    export_job.remove_old_exports()
    assert not (map_export_root / 'not made yet').exists()


def test_only_exports_are_removed(map_export_root, tmp_path):
    """What is old in the directory of exports, and is not an export, is left: a directory by another name, and a
    link by an export's name to a directory somewhere else."""
    new_export('A')
    other = map_export_root / 'someone-elses-directory'
    other.mkdir()
    (other / 'file').write_text('kept')
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (elsewhere / 'precious').write_text('kept')
    link = map_export_root / ('f' * 32)
    link.symlink_to(elsewhere, target_is_directory=True)
    for path in (other, elsewhere):
        age(path)

    export_job.remove_old_exports()
    assert (other / 'file').read_text() == 'kept'
    assert (elsewhere / 'precious').read_text() == 'kept'
    # And a link is not an export.
    with pytest.raises(export_job.ExportNotFound):
        export_job.save_layer('f' * 32, 0, make_image())


def test_export_directory_is_this_users(map_export_root, tmp_path, monkeypatch):
    """Exports are kept in a directory made for this user alone, and never through a link: anyone may make things
    in /var/tmp, and a link there would have exports written, and old ones removed, wherever it leads."""
    export_id = new_export('A')
    assert stat.S_IMODE(map_export_root.stat().st_mode) == 0o700
    assert stat.S_IMODE((map_export_root / export_id).stat().st_mode) == 0o700

    # One which others could read is closed to them when it is next used.
    os.chmod(map_export_root, 0o755)
    new_export('A')
    assert stat.S_IMODE(map_export_root.stat().st_mode) == 0o700

    # A link where the directory should be.
    elsewhere = tmp_path / 'elsewhere'
    (elsewhere / ('a' * 32)).mkdir(parents=True)
    age(elsewhere / ('a' * 32))
    linked = tmp_path / 'linked-root'
    linked.symlink_to(elsewhere, target_is_directory=True)
    monkeypatch.setattr(export_job, 'EXPORT_ROOT', linked)
    with pytest.raises(export_job.ExportStorageError):
        new_export('A')
    with pytest.raises(export_job.ExportStorageError):
        export_job.remove_old_exports()
    with pytest.raises(export_job.ExportStorageError):
        export_job.save_layer('a' * 32, 0, make_image())
    # Nothing was made, or removed, where the link leads.
    assert [i.name for i in elsewhere.iterdir()] == ['a' * 32]

    # A file where the directory should be.
    not_a_directory = tmp_path / 'a-file'
    not_a_directory.write_text('')
    monkeypatch.setattr(export_job, 'EXPORT_ROOT', not_a_directory)
    with pytest.raises(export_job.ExportStorageError):
        new_export('A')


@pytest.mark.asyncio
async def test_exports_of_waiting_jobs_are_kept(async_client, map_export_root):
    """An export whose Job is waiting is kept however old it is: it may wait behind another Job for longer than an
    export is kept, and its images are what the Job is to work from.  One whose Job was cancelled is removed at
    once."""
    waiting, cancelled, finished = new_export('A'), new_export('A'), new_export('A')
    for export_id in (waiting, cancelled, finished):
        export_job.save_layer(export_id, 0, make_image())
    await jobs.wait_for_job(export_job.start_export(finished), timeout=60)
    # Queued, and not run: nothing takes Jobs from the queue in a test until one is waited for.
    waiting_job = export_job.start_export(waiting)
    jobs.cancel_job(export_job.start_export(cancelled))
    for export_id in (waiting, finished):
        age(map_export_root / export_id)

    export_job.remove_old_exports()
    assert sorted(i.name for i in map_export_root.iterdir()) == [waiting]
    assert (map_export_root / waiting / 'layer-000').is_file()

    # It is still there for its Job, which makes the PDF.
    assert (await jobs.wait_for_job(waiting_job, timeout=60))['status'] == 'complete'
    assert export_job.get_export_pdf(waiting).is_file()


@pytest.mark.asyncio
async def test_remove_export(async_client, map_export_root):
    """An export which is stopped is removed, with the images which were sent, whatever step it was at."""
    # Before its PDF was asked for.
    export_id = new_export('A', 'B')
    export_job.save_layer(export_id, 0, make_image())
    request, response = await async_client.delete(f'/api/map/export/{export_id}')
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not (map_export_root / export_id).exists()
    request, response = await async_client.delete(f'/api/map/export/{export_id}')
    assert response.status_code == HTTPStatus.NOT_FOUND

    # While its Job waited: the Job is cancelled, and never runs.
    export_id = new_export('A')
    export_job.save_layer(export_id, 0, make_image())
    job_id = export_job.start_export(export_id)
    export_job.remove_export(export_id)
    assert not (map_export_root / export_id).exists()
    assert (await jobs.wait_for_job(job_id, timeout=60))['status'] == 'cancelled'

    # After its PDF was made.
    export_id = new_export('A')
    export_job.save_layer(export_id, 0, make_image())
    await jobs.wait_for_job(export_job.start_export(export_id), timeout=60)
    export_job.remove_export(export_id)
    assert not (map_export_root / export_id).exists()

    with pytest.raises(export_job.ExportNotFound):
        export_job.remove_export('0' * 32)


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
    # And, with every step done, before and after the PDF is written: when the work may still be stopped.
    assert seen == [0, 25, 50, 75, 100, 100, 100]


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
    """A cancelled Job stops between two layers, makes no PDF, and removes the images.  It is not over until the
    work has stopped: the next Job is not to start beside it."""
    export_id = new_export('A', 'B', 'C')
    for index in range(3):
        export_job.save_layer(export_id, index, make_image())
    job_id = export_job.start_export(export_id)

    # The work is held while its first layer is looked at.
    real_check = export._check_layer
    checked, looking, go_on = [], threading.Event(), threading.Event()

    def check_layer(layer, width, height):
        checked.append(layer.name)
        looking.set()
        assert go_on.wait(30)
        return real_check(layer, width, height)

    monkeypatch.setattr(export, '_check_layer', check_layer)
    waiting = asyncio.ensure_future(jobs.wait_for_job(job_id, timeout=60))
    for _ in range(200):
        if looking.is_set():
            break
        await asyncio.sleep(0.02)
    assert looking.is_set()

    # Cancelled, as from another process.  (Not `cancel_job` here: it logs while it holds the Jobs' lock, and
    # this test's log is written to the running Job, which takes that lock.)
    jobs._update_job(job_id, cancel_requested=True)
    await asyncio.sleep(0.5)
    # The work has not stopped, so neither has the Job: its images are still there.
    assert jobs.get_job(job_id)['status'] == 'running'
    assert not waiting.done()
    assert (map_export_root / export_id / 'layer-000').is_file()

    go_on.set()
    job = await waiting
    assert job['status'] == 'cancelled'
    # When the Job is over, so is the work: one layer was looked at, and the images are gone.
    assert checked == ['A']
    assert sorted(i.name for i in (map_export_root / export_id).iterdir()) == ['meta.json']
    with pytest.raises(export_job.ExportNotReady, match='cancelled'):
        export_job.get_export_pdf(export_id)


@pytest.mark.asyncio
async def test_job_cancelled_as_the_pdf_is_written(async_client, map_export_root, monkeypatch):
    """A Job cancelled after its last layer, while the sheet is drawn or the PDF written, makes no PDF either."""
    export_id = new_export('A')
    export_job.save_layer(export_id, 0, make_image())
    job_id = export_job.start_export(export_id)
    real_insert = export._insert_layer

    def insert_layer(*args):
        real_insert(*args)
        jobs._update_job(job_id, cancel_requested=True)

    monkeypatch.setattr(export, '_insert_layer', insert_layer)
    job = await jobs.wait_for_job(job_id, timeout=60)
    assert job['status'] == 'cancelled'
    assert sorted(i.name for i in (map_export_root / export_id).iterdir()) == ['meta.json']


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


class NeverCancelled:
    """A Job which was not cancelled, as one is which ends because the API is stopping."""

    @staticmethod
    def cancel_requested() -> bool:
        return False

    @staticmethod
    def set_progress(_: float):
        pass


def test_work_stops_when_it_is_told_to(map_export_root):
    """The work of a Job which ended without being cancelled (the API is stopping) stops between two layers when
    it is told to: the API waits for it, and is not to wait for all of a PDF."""
    export_id = new_export('A', 'B')
    for index in range(2):
        export_job.save_layer(export_id, index, make_image())
    directory = map_export_root / export_id
    stop = threading.Event()
    stop.set()
    with pytest.raises(export_job.ExportCancelled):
        export_job._make_pdf(directory, NeverCancelled, stop)
    assert sorted(i.name for i in directory.iterdir()) == ['meta.json']
    # Not told to, it makes the PDF.
    export_id = new_export('A')
    export_job.save_layer(export_id, 0, make_image())
    export_job._make_pdf(map_export_root / export_id, NeverCancelled, threading.Event())
    assert sorted(i.name for i in (map_export_root / export_id).iterdir()) == ['map.pdf', 'meta.json']


def test_files_of_an_export_are_written_whole(map_export_root, monkeypatch):
    """What is said of an export, and each image, is all there or is what was there before: another request
    may read it while it is written.  A write which fails leaves nothing behind."""
    export_id = new_export('A')
    directory = map_export_root / export_id
    before = (directory / 'meta.json').read_text()

    def replace(*_):
        raise OSError('The disk is full')

    with monkeypatch.context() as patch:
        patch.setattr(export_job.os, 'replace', replace)
        with pytest.raises(OSError):
            export_job.save_layer(export_id, 0, make_image())
        with pytest.raises(OSError):
            export_job._write_meta(directory, {'layers': []})
    assert sorted(i.name for i in directory.iterdir()) == ['meta.json']
    assert (directory / 'meta.json').read_text() == before
    export_job.save_layer(export_id, 0, make_image())
    assert sorted(i.name for i in directory.iterdir()) == ['layer-000', 'meta.json']


@pytest.mark.asyncio
async def test_job_removes_old_exports(async_client, map_export_root):
    """Old exports are removed when a PDF is made, as well as when an export begins: the last export of a day
    is not to keep the one before it."""
    old = new_export('A')
    export_id = new_export('A')
    age(map_export_root / old)
    export_job.save_layer(export_id, 0, make_image())
    job = await jobs.wait_for_job(export_job.start_export(export_id), timeout=60)
    assert job['status'] == 'complete'
    assert sorted(i.name for i in map_export_root.iterdir()) == [export_id]
