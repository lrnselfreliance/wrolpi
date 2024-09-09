import asyncio
import inspect
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING

from wrolpi.api_utils import api_app, perpetual_signal
from wrolpi.common import logger

logger = logger.getChild(__name__)

TASK_HANDLERS = dict()

if TYPE_CHECKING:
    api_app.shared_ctx.task_queue: list  # noqa


def auto_background_task(func: callable) -> Callable:
    """Capture all calls to this async function, add them to a multiprocessing.Queue which will be executed by
    `task_handler` and Sanic.

    Removes any competing calls to this function which have not yet been processed.  That means that only the final
    call to the wrapped function will be processed.  This is useful for configs; we only want to save a config once
    after all DB changes have been applied.  We don't want to save a config multiple times when many tags are being
    added for example, only once they have all been added.

    The task can be handled by any Sanic process (see `task_handler`) because args/kwargs are sent via
    multiprocessing.Queue, so they must be pickle-able.

    If you await the returned coroutine, then the task will be handled immediately and the background task will be
    cancelled.

    @warning: Uses the function's name as the task name, so each wrapped function must have a unique name.

    >>> @auto_background_task
    >>> async def slow_func(count):
    >>>     pass
    >>>
    >>> slow_func(1)
    >>> slow_func(2)
    >>> slow_func(3)
    # Only 3 is processed, unless 1 and 2 finish very quickly.

    # The function is run immediately, and the background task is cancelled.
    >>> await slow_func(4)()
    """
    task_name = func.__name__
    TASK_HANDLERS[task_name] = func

    @wraps(func)
    def wrapped(*args, **kwargs):
        task_queue = api_app.shared_ctx.task_queue

        # Remove any conflicting task calls. We only want to run the latest task.
        have_conflicts = True
        while have_conflicts:
            have_conflicts = False
            for idx, task_data in enumerate(task_queue):
                if task_data['task_name'] == task_name:
                    task_queue.pop(idx)
                    have_conflicts = True
                    break

        # Add task data to the queue.
        data = dict(task_name=task_name, args=args, kwargs=kwargs)
        task_queue.append(data)
        logger.debug(f'auto_background_task added: {task_name}')

        async def task_wrapper():
            # Task was awaited, no need to run it in the background.
            if data in task_queue:
                task_queue.remove(data)
            return await func(*args, **kwargs)

        # Return an async function that can be awaited, and will cancel the background task.
        return task_wrapper

    return wrapped


TASK_HANDLER_STARTED = False


def _add_task(coro, name):
    api_app.add_task(coro, name=name)


@perpetual_signal(sleep=0.1)
async def task_handler():
    global TASK_HANDLER_STARTED
    TASK_HANDLER_STARTED = True

    try:
        task_data = api_app.shared_ctx.task_queue.pop(0)
    except IndexError:
        # No tasks yet.
        return

    task_name, args, kwargs = task_data['task_name'], task_data['args'], task_data['kwargs']
    # Get the function wrapped by `register_task_handler`
    handler = TASK_HANDLERS[task_name]
    if not inspect.iscoroutinefunction(handler):
        coro = asyncio.to_thread(handler, *args, **kwargs)
    else:
        coro = handler(*args, **kwargs)
    # # Add the coroutine to Sanic so that it does not exit before task has completed.
    _add_task(coro, name=task_name)

    logger.info(f'task_handler started: {task_name}')
