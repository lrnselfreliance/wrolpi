import asyncio
import logging
from http import HTTPStatus

import pytest

from wrolpi import jobs
from wrolpi.errors import InvalidJob, UnknownJob
from wrolpi.jobs import register_job, enqueue_job, wait_for_job, get_job, get_current_job, cancel_job, \
    process_job_queue, get_jobs

test_logger = logging.getLogger('wrolpi.test.jobs')

order = []


@register_job('test_add')
async def job_add(a: int, b: int):
    order.append(('add', a, b))
    test_logger.warning(f'adding {a} and {b}')
    return a + b


@register_job('test_sync')
def job_sync(value: str):
    return value.upper()


@register_job('test_fail')
async def job_fail(message: str):
    raise RuntimeError(message)


@register_job('test_progress')
async def job_progress():
    job = get_current_job()
    job.log('first line')
    job.set_progress(42)
    return {'job_id': job.id}


@register_job('test_slow')
async def job_slow(seconds: float):
    await asyncio.sleep(seconds)
    return 'done'


@register_job('test_command')
async def job_command():
    job = get_current_job()
    result = await job.run_command(('sh', '-c', 'echo out1; echo out2; echo err1 >&2'))
    return result.return_code


@register_job('test_slow_command')
async def job_slow_command():
    job = get_current_job()
    result = await job.run_command(('sleep', '30'))
    return result.cancelled


@pytest.mark.asyncio
async def test_jobs_fifo(async_client):
    """Jobs run in the order they were queued; sync and async handlers both work; results are stored."""
    order.clear()
    first = enqueue_job('test_add', a=1, b=2)
    second = enqueue_job('test_add', a=3, b=4)
    third = enqueue_job('test_sync', value='abc')

    for job_id in (first, second, third):
        assert get_job(job_id)['status'] == jobs.PENDING

    assert (await wait_for_job(third))['status'] == jobs.COMPLETE
    assert order == [('add', 1, 2), ('add', 3, 4)]
    assert get_job(first)['result'] == 3
    assert get_job(second)['result'] == 7
    assert get_job(third)['result'] == 'ABC'
    assert get_job(first)['progress'] == 100
    assert get_job(first)['started_at'] and get_job(first)['finished_at']
    assert [i['id'] for i in get_jobs()] == [first, second, third]


@pytest.mark.asyncio
async def test_jobs_capture_logging(async_client):
    """`logging` emitted while a Job runs is captured into that Job's log, and only that Job's."""
    a = enqueue_job('test_add', a=5, b=6)
    b = enqueue_job('test_add', a=7, b=8)
    await wait_for_job(b)
    a_log = get_job(a)['log']
    assert any('adding 5 and 6' in i for i in a_log), a_log
    assert not any('adding 7 and 8' in i for i in a_log), a_log
    assert any('adding 7 and 8' in i for i in get_job(b)['log'])


@pytest.mark.asyncio
async def test_jobs_failure(async_client):
    """A handler exception fails the Job and records the error; the queue keeps going."""
    failed = enqueue_job('test_fail', message='boom')
    after = enqueue_job('test_sync', value='after')
    record = await wait_for_job(after)
    assert record['status'] == jobs.COMPLETE
    failed = get_job(failed)
    assert failed['status'] == jobs.FAILED
    assert failed['error'] == 'boom'
    assert any('boom' in i for i in failed['log'])


@pytest.mark.asyncio
async def test_jobs_context(async_client):
    """The handler can log, report progress, and learn its own id through `get_current_job`."""
    job_id = enqueue_job('test_progress', description='Progress test')
    record = await wait_for_job(job_id)
    assert record['result'] == {'job_id': job_id}
    assert record['description'] == 'Progress test'
    assert 'first line' in record['log']
    assert record['progress'] == 100  # Completion sets 100.
    assert get_current_job() is None, 'No Job is running outside of the worker'


@pytest.mark.asyncio
async def test_jobs_run_command_captured(async_client):
    """stdout and stderr of a Job subprocess land in the Job log."""
    job_id = enqueue_job('test_command')
    record = await wait_for_job(job_id)
    assert record['status'] == jobs.COMPLETE, record
    assert record['result'] == 0
    assert 'out1' in record['log'] and 'out2' in record['log'] and 'err1' in record['log']


@pytest.mark.asyncio
async def test_jobs_cancel_pending(async_client):
    """A pending Job is cancelled immediately and never runs."""
    order.clear()
    job_id = enqueue_job('test_add', a=1, b=1)
    record = cancel_job(job_id)
    assert record['status'] == jobs.CANCELLED
    assert record['finished_at']
    assert await process_job_queue() == 1, 'The queued id is consumed'
    assert order == [], 'The cancelled Job did not run'
    assert get_job(job_id)['status'] == jobs.CANCELLED


@pytest.mark.asyncio
async def test_jobs_cancel_running(async_client):
    """A running Job is cancelled the next time the worker polls; its subprocess is killed."""
    job_id = enqueue_job('test_slow_command')
    task = asyncio.create_task(process_job_queue())
    # Wait for the Job to actually be running.
    for _ in range(200):
        if get_job(job_id)['status'] == jobs.RUNNING:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError('Job never started')

    record = cancel_job(job_id)
    assert record['cancel_requested'] is True
    await asyncio.wait_for(task, timeout=5)
    record = get_job(job_id)
    assert record['status'] == jobs.CANCELLED
    assert 'Cancelled' in record['log']


@pytest.mark.asyncio
async def test_jobs_validation(async_client):
    with pytest.raises(InvalidJob):
        enqueue_job('does_not_exist')
    with pytest.raises(InvalidJob):
        enqueue_job('test_add', a=object(), b=1)
    with pytest.raises(UnknownJob):
        get_job('nope')
    with pytest.raises(UnknownJob):
        cancel_job('nope')


@pytest.mark.asyncio
async def test_jobs_prune(async_client):
    """Only the newest finished Jobs are kept."""
    old_limit = jobs.JOB_HISTORY_LIMIT
    jobs.JOB_HISTORY_LIMIT = 2
    try:
        ids = [enqueue_job('test_sync', value=str(i)) for i in range(3)]
        await wait_for_job(ids[-1])
        # A new enqueue triggers the prune.
        newest = enqueue_job('test_sync', value='x')
        remaining = {i['id'] for i in get_jobs()}
        assert ids[0] not in remaining
        assert ids[1] in remaining and ids[2] in remaining and newest in remaining
    finally:
        jobs.JOB_HISTORY_LIMIT = old_limit


@pytest.mark.asyncio
async def test_jobs_api(async_client):
    """Jobs can be listed, fetched, and cancelled over the API."""
    job_id = enqueue_job('test_slow', description='Sleepy', seconds=30)

    request, response = await async_client.get('/api/jobs')
    assert response.status == HTTPStatus.OK
    assert [i['id'] for i in response.json['jobs']] == [job_id]

    request, response = await async_client.get(f'/api/jobs/{job_id}')
    assert response.status == HTTPStatus.OK
    assert response.json['job']['description'] == 'Sleepy'
    assert response.json['job']['status'] == jobs.PENDING

    request, response = await async_client.delete(f'/api/jobs/{job_id}')
    assert response.status == HTTPStatus.OK
    assert response.json['job']['status'] == jobs.CANCELLED

    request, response = await async_client.get('/api/jobs/nope')
    assert response.status == HTTPStatus.NOT_FOUND
