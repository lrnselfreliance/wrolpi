"""
Wrap a function with `timeout` to kill it after some amount of seconds, the wrapped function is run in it's own
process.  If the timeout is reached, kill the process and raise a TimeoutError.

Log any errors in the global logger.  If the worker process raises an Exception, raise an Exception sharing it's
description, log the traceback.

>>> @timeout(5)
>>> def long_running_function():
>>>    while True:
>>>        # Run infinitely
>>>        time.sleep(1)

>>> long_running_function()
TimeoutError()
"""
import multiprocessing.connection
import time
import traceback
from datetime import datetime, timedelta
from functools import wraps
from multiprocessing import Process, Pipe

from api.common import logger

logger = logger.getChild(__name__)


class WorkerException(Exception):
    pass


TEST_TIMEOUT = None
KILL_ATTEMPTS = 100


def timeout(seconds: float) -> callable:
    """
    Create a worker process, let it run until the timeout, then kill it.  If the worker isn't killed, return
    it's result or exception.  If it is killed, raise a TimeoutError.
    """

    def wrapper(func):

        def worker_wrapper(pipe: multiprocessing.connection.Connection, *args, **kwargs):
            """
            Wraps a worker function so we can catch it's Exception, or return its results.
            """
            to_send = {}
            try:
                result = func(*args, **kwargs)
                to_send['result'] = result
            except Exception as e:
                to_send.update({'exception': str(e), 'traceback': traceback.format_exc()})
            finally:
                pipe.send(to_send)

        @wraps(func)
        def wrapped(*args, **kwargs):
            # unittest may override the timeout
            _seconds = TEST_TIMEOUT or seconds

            # Start the worker_wrapper, give it a way to communicate back.
            parent_conn, child_conn = Pipe()
            args = (child_conn,) + args
            worker = Process(target=worker_wrapper, args=args, kwargs=kwargs)
            worker.start()

            # Continually attempt to get a result until the timeout is reached.
            kill_time = datetime.utcnow() + timedelta(seconds=_seconds)
            while True:
                if not worker.is_alive():
                    # Worker exited.
                    break
                if not datetime.utcnow() < kill_time:
                    # Timeout was reached.
                    break
                if parent_conn.poll(0.1):
                    # Result is waiting.
                    break

            # Get the result, if any.
            result = None
            if parent_conn.poll(0):
                result = parent_conn.recv()

            attempts = 0
            while worker.is_alive():
                # Worker has run out of time.
                worker.kill()
                time.sleep(0.1)
                attempts += 1
                if attempts > KILL_ATTEMPTS:
                    logger.warning(f'Failed to kill worker! {func}')
                    break

            worker.join()

            if result:
                if 'result' in result:
                    return result['result']
                elif 'exception' in result:
                    exception = result['exception']
                    _traceback = result['traceback']
                    logger.warning(f'Traceback from worker: {_traceback}')
                    raise WorkerException(f'Exception from worker: {exception}')

            if attempts > 0:
                raise TimeoutError(f'Killed worker after {_seconds} seconds: {func}')

        return wrapped

    return wrapper
