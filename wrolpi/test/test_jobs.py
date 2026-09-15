import asyncio
import logging
from unittest import mock
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


@pytest.mark.asyncio
async def test_jobs_claim_is_atomic(async_client):
    """The worker claims a Job (PENDING -> RUNNING) in one step under the lock, so a cancel that
    lands first wins and the Job never runs; a cancel that lands after only requests a stop."""
    from wrolpi.jobs import _claim_job

    cancelled_first = enqueue_job('test_sync', value='a')
    cancel_job(cancelled_first)
    assert _claim_job(cancelled_first) is None, 'A cancelled Job cannot be claimed'
    assert get_job(cancelled_first)['status'] == jobs.CANCELLED, 'The claim must not promote it to RUNNING'

    claimed = enqueue_job('test_sync', value='b')
    record = _claim_job(claimed)
    assert record['status'] == jobs.RUNNING and record['pid'] and record['started_at']
    assert get_job(claimed)['status'] == jobs.RUNNING
    assert _claim_job(claimed) is None, 'A Job is claimed once'
    # Cancelling a claimed Job only asks it to stop.
    assert cancel_job(claimed)['status'] == jobs.RUNNING
    assert get_job(claimed)['cancel_requested'] is True


@pytest.mark.asyncio
async def test_jobs_pending_limit(async_client):
    """The queue refuses new Jobs past a pending cap, so a runaway client cannot grow shared memory."""
    with mock.patch.object(jobs, 'JOB_PENDING_LIMIT', 2):
        first = enqueue_job('test_slow', seconds=30)
        second = enqueue_job('test_slow', seconds=30)
        with pytest.raises(InvalidJob, match='pending'):
            enqueue_job('test_slow', seconds=30)
        # A cancelled Job no longer counts.
        cancel_job(first)
        third = enqueue_job('test_slow', seconds=30)
    for job_id in (second, third):
        cancel_job(job_id)
    assert await process_job_queue() == 3, 'Cancelled ids are drained as no-ops'
    assert [i['status'] for i in get_jobs()] == [jobs.CANCELLED] * 3


@pytest.mark.asyncio
async def test_jobs_run_command_cancel_semantics(async_client):
    """A Job's subprocess runs in its own session (the whole group dies with it), and a killed
    command raises rather than returning a result a handler could mistake for a normal exit."""
    from wrolpi.cmd import CommandResult
    from wrolpi.jobs import JobContext

    context = JobContext('test-1', 'test')
    killed = CommandResult(return_code=-9, cancelled=True, stdout=b'', stderr=b'', elapsed=1)
    with mock.patch('wrolpi.cmd.run_command', return_value=killed) as mock_run:
        with pytest.raises(asyncio.CancelledError):
            await context.run_command(('sleep', '30'))
    assert mock_run.call_args.kwargs['start_new_session'] is True
