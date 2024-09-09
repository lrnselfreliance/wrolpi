import asyncio
import multiprocessing
import time

import mock
import pytest

from wrolpi.tasks import auto_background_task

async_count = multiprocessing.Value('i', 0)
async_args = None


@auto_background_task
async def slow_async_task(*args, **kwargs):
    print(f'slow_async_task called: {args=} {kwargs=}')
    await asyncio.sleep(1)
    global async_args
    async_args = (args, kwargs)
    async_count.value += 1
    print('slow_async_task done')


@pytest.mark.asyncio
async def test_task_handler_async(async_client, await_tasks):
    # Can call `slow_task` but it does not run yet.
    slow_async_task('1', two=2)
    assert async_count.value == 0
    # Wait for tasks to complete.
    await await_tasks()
    # Task ran, args were passed.
    assert async_count.value == 1
    assert async_args == (('1',), {'two': 2})

    # Calling `slow_task` multiple times causes only the last call to run.
    slow_async_task('2')
    slow_async_task('3')
    slow_async_task('4')
    assert async_count.value == 1
    # Wait for tasks to complete.
    await await_tasks()
    # Last call was only task that ran.
    assert async_count.value == 2
    assert async_args == (('4',), {})


sync_count = 0
sync_args = None


@auto_background_task
def slow_sync_task(*args, **kwargs):
    print(f'slow_sync_task called: {args=} {kwargs=}')
    time.sleep(1)
    global sync_args, sync_count
    sync_args = (args, kwargs)
    sync_count += 1
    print('slow_sync_task done')


@pytest.mark.asyncio
async def test_task_handler_sync(async_client, await_tasks):
    # Can call `slow_task` but it does not run yet.
    slow_sync_task('1', two=2)
    assert sync_count == 0
    # Wait for tasks to complete.
    await await_tasks()
    # Task ran, args were passed.
    assert sync_count == 1
    assert sync_args == (('1',), {'two': 2})

    # Calling `slow_task` multiple times causes only the last call to run.
    slow_sync_task('2')
    slow_sync_task('3')
    slow_sync_task('4')
    assert sync_count == 1
    # Wait for tasks to complete.
    await await_tasks()
    # Last call was only task that ran.
    assert sync_count == 2
    assert sync_args == (('4',), {})


@pytest.mark.asyncio
async def test_too_long_task(async_client, await_tasks):
    """A task that is too slow throws an error when testing."""

    @auto_background_task
    async def too_long_task():
        await asyncio.sleep(30)

    too_long_task()

    with pytest.raises(RuntimeError):
        # `await_tasks` does not wait forever.
        await await_tasks(5)

    # Cancel background task
    task = async_client.sanic_app.get_task('too_long_task')
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_awaited_task(async_client, await_tasks):
    """A task can be awaited immediately and won't be run in background."""
    finished = False

    with mock.patch('wrolpi.tasks._add_task') as mocked:
        mocked.side_effect = Exception('background task should have been cancelled')

        @auto_background_task
        async def slow_task():
            await asyncio.sleep(1)
            nonlocal finished
            finished = True

        await slow_task()()
        assert finished
