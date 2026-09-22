"""In-memory FIFO queue of background Jobs.

A Job is a call of a *registered* function with JSON-able kwargs.  Any Sanic worker may enqueue a
Job; the perpetual process runs them one at a time, in order.  Python logging emitted
while a Job runs, and the output of subprocesses started through `JobContext.run_command`, are
captured into the Job's log.  A caller may wait for a Job, poll it, or cancel it.

Jobs are never written to disk: when the API restarts they are lost.

>>> @register_job('example')
>>> async def example(path: str):
>>>     job = get_current_job()
>>>     job.set_progress(50)
>>>     await job.run_command(('ls', path))

>>> job_id = enqueue_job('example', description='List a directory', path='/tmp')
>>> await wait_for_job(job_id)

Functions are registered by name (rather than enqueued as objects) because kwargs and the call
must cross the process boundary between Sanic workers; a name and JSON kwargs always can.
"""
import asyncio
import contextvars
import inspect
import json
import logging
import multiprocessing
import os
import pathlib
import queue
import time
import uuid
from collections import deque
from functools import partial
from http import HTTPStatus
from typing import Callable, Dict, List, Optional

from sanic import Blueprint
from sanic.request import Request
from sanic_ext.extensions.openapi import openapi

from wrolpi.api_utils import api_app, json_response, perpetual_signal
from wrolpi.common import logger
from wrolpi.dates import now
from wrolpi.errors import UnknownJob, InvalidJob
from wrolpi.events import Events
from wrolpi.schema import JSONErrorResponse
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)

JOB_HANDLERS: Dict[str, Callable] = dict()

PENDING = 'pending'
RUNNING = 'running'
COMPLETE = 'complete'
FAILED = 'failed'
CANCELLED = 'cancelled'
FINISHED_STATUSES = (COMPLETE, FAILED, CANCELLED)

# Only the tail of a Job's log is kept; ffmpeg alone can emit thousands of lines.
JOB_LOG_LINES = 200
# Finished Jobs kept for the UI/API before the oldest are forgotten.
JOB_HISTORY_LIMIT = 100
# Pending Jobs allowed at once; `enqueue_job` refuses past this so a runaway client cannot grow
# shared memory without bound.
JOB_PENDING_LIMIT = 100
# How often the running Job checks whether it has been cancelled from another process.
JOB_CANCEL_POLL_SECONDS = 0.05 if PYTEST else 1
# The Job log lives in this process; it is copied to the shared dict at most this often.
JOB_LOG_FLUSH_SECONDS = 0 if PYTEST else 0.5


def _jobs() -> dict:
    try:
        return api_app.shared_ctx.jobs
    except AttributeError:
        raise RuntimeError('Sanic shared_ctx has not been initialized.  If testing, use `async_client` fixture.')


def _queue():
    return api_app.shared_ctx.jobs_queue


def _lock() -> multiprocessing.Lock:
    return api_app.shared_ctx.jobs_lock


def register_job(name: str):
    """Register a function that can be run as a Job by `name`.

    The function may be sync or async, and is called with the kwargs given to `enqueue_job`.  Use
    `get_current_job()` inside the function for logging, progress, subprocesses, and cancellation.
    The wrapped function gains an `enqueue(description=None, **kwargs)` method.
    """

    def wrapper(func: Callable):
        if name in JOB_HANDLERS and not PYTEST:
            raise RuntimeError(f'register_job: job name already taken {name}')
        JOB_HANDLERS[name] = func
        setattr(func, 'enqueue', partial(enqueue_job, name))
        return func

    return wrapper


def enqueue_job(name: str, description: str = None, **kwargs) -> str:
    """Add a Job to the end of the queue.  Returns its id.

    @raise InvalidJob: when `name` is not registered, or kwargs are not JSON serializable.
    """
    if name not in JOB_HANDLERS:
        raise InvalidJob(f'No job is registered with the name {name!r}')
    try:
        json.dumps(kwargs)
    except (TypeError, ValueError) as e:
        raise InvalidJob(f'Job kwargs must be JSON serializable: {e}')

    job_id = f'{name}-{uuid.uuid4().hex[:8]}'
    record = dict(
        id=job_id,
        name=name,
        description=description or name,
        kwargs=kwargs,
        status=PENDING,
        created_at=now().isoformat(),
        started_at=None,
        finished_at=None,
        error=None,
        progress=None,
        result=None,
        log=[],
        pid=None,
        cancel_requested=False,
    )
    with _lock():
        pending = sum(1 for i in _jobs().values() if i['status'] == PENDING)
        if pending >= JOB_PENDING_LIMIT:
            raise InvalidJob(f'Too many pending jobs ({pending}); try again once some have finished')
        _jobs()[job_id] = record
        _prune_finished_jobs()
    _queue().put_nowait(job_id)
    logger.info(f'enqueue_job: {job_id} ({description or name})')
    return job_id


def get_job(job_id: str) -> dict:
    """@raise UnknownJob: when no Job has this id."""
    record = _jobs().get(job_id)
    if not record:
        raise UnknownJob(f'Job {job_id} does not exist')
    return dict(record)


def get_jobs() -> List[dict]:
    """All Jobs, oldest first."""
    return sorted((dict(i) for i in _jobs().values()), key=lambda i: i['created_at'])


def _update_job(job_id: str, **changes):
    """Manager dict values are copies; a change must be written back as a whole record."""
    with _lock():
        record = _jobs().get(job_id)
        if record is None:
            return
        record = dict(record)
        record.update(changes)
        _jobs()[job_id] = record


def _prune_finished_jobs():
    """Forget the oldest finished Jobs beyond `JOB_HISTORY_LIMIT`.  The caller holds the lock."""
    jobs = _jobs()
    finished = sorted((i for i in jobs.values() if i['status'] in FINISHED_STATUSES),
                      key=lambda i: i['finished_at'] or '')
    for record in finished[:max(0, len(finished) - JOB_HISTORY_LIMIT)]:
        del jobs[record['id']]


def cancel_job(job_id: str) -> dict:
    """Cancel a pending Job immediately, or ask the running Job to stop.

    A running Job's handler is cancelled (its `run_command` subprocess is killed) the next time the
    worker polls.  Finished Jobs are unchanged.
    """
    with _lock():
        record = _jobs().get(job_id)
        if not record:
            raise UnknownJob(f'Job {job_id} does not exist')
        record = dict(record)
        if record['status'] == PENDING:
            record.update(status=CANCELLED, finished_at=now().isoformat())
            logger.info(f'cancel_job: cancelled pending {job_id}')
        elif record['status'] == RUNNING:
            record['cancel_requested'] = True
            logger.info(f'cancel_job: requested cancel of running {job_id}')
        _jobs()[job_id] = record
    return record


def _claim_job(job_id: str) -> Optional[dict]:
    """Move a Job from PENDING to RUNNING in one step under the lock; returns the running record,
    or None when the Job is no longer pending (cancelled while queued, or already claimed)."""
    with _lock():
        record = _jobs().get(job_id)
        if not record or record['status'] != PENDING:
            return None
        record = dict(record)
        record.update(status=RUNNING, started_at=now().isoformat(), pid=os.getpid())
        _jobs()[job_id] = record
        return record


def fail_orphaned_jobs() -> int:
    """Mark RUNNING Jobs owned by another (dead) process as FAILED.  Called by the perpetual process when it
    starts: only it runs Jobs, so any RUNNING record not carrying its pid belongs to a predecessor that died
    mid-Job.  Returns how many were failed."""
    count = 0
    with _lock():
        for job_id, record in list(_jobs().items()):
            if record['status'] == RUNNING and record.get('pid') != os.getpid():
                record = dict(record)
                record.update(status=FAILED, finished_at=now().isoformat(),
                              error='The process running this Job exited before it finished')
                _jobs()[job_id] = record
                count += 1
    if count:
        logger.warning(f'fail_orphaned_jobs: failed {count} Job(s) left running by a previous process')
    return count


def _cancel_requested(job_id: str) -> bool:
    record = _jobs().get(job_id)
    return bool(record and record.get('cancel_requested'))


class JobContext:
    """The running Job, available to its handler via `get_current_job()`."""

    def __init__(self, job_id: str, name: str):
        self.id = job_id
        self.name = name
        self._log: deque = deque(maxlen=JOB_LOG_LINES)
        self._last_flush = 0.0
        self._dirty = False

    def log(self, line: str):
        """Append a line to the Job's log.  Must never call `logger` (the log handler would recurse)."""
        self._log.append(str(line).rstrip())
        self._dirty = True
        if time.monotonic() - self._last_flush >= JOB_LOG_FLUSH_SECONDS:
            self.flush()

    def flush(self):
        if not self._dirty:
            return
        self._last_flush = time.monotonic()
        self._dirty = False
        _update_job(self.id, log=list(self._log))

    def set_progress(self, percent: Optional[float]):
        """Report progress 0-100 to the UI."""
        if percent is not None:
            percent = max(0.0, min(100.0, float(percent)))
        _update_job(self.id, progress=percent)

    def cancel_requested(self) -> bool:
        return _cancel_requested(self.id)

    async def run_command(self, cmd: tuple[str | pathlib.Path, ...], stdout_callback: Callable = None, **kwargs):
        """`wrolpi.cmd.run_command` whose stdout lines (live) and stderr tail (on exit) are
        captured into this Job's log.  `stdout_callback` still receives each stdout line."""
        from wrolpi.cmd import run_command

        def _callback(line: str):
            self.log(line)
            if stdout_callback:
                stdout_callback(line)

        # Its own session: killing the command kills anything it spawned, as elsewhere in WROLPi.
        kwargs.setdefault('start_new_session', True)
        result = await run_command(cmd, stdout_callback=_callback, **kwargs)
        if result.stderr:
            for line in result.stderr.decode(errors='replace').splitlines()[-JOB_LOG_LINES:]:
                if line.strip():
                    self.log(line)
        self.flush()
        if result.cancelled:
            # `run_command` swallows the cancellation and returns; a handler checking return codes
            # must not mistake a killed command for a normal exit.
            raise asyncio.CancelledError(f'Command was cancelled: {cmd[0]}')
        return result


_current_job: contextvars.ContextVar[Optional[JobContext]] = contextvars.ContextVar('current_job', default=None)


def get_current_job() -> Optional[JobContext]:
    """The Job whose handler is running in this task, or None outside of a Job."""
    return _current_job.get()


class JobLogHandler(logging.Handler):
    """Copies log records emitted inside a running Job into that Job's log.

    The context variable is set on the task that runs the handler, so only records from the Job
    (and tasks it spawns) are captured, not those of the other coroutines in this process."""

    def emit(self, record: logging.LogRecord):
        job = _current_job.get()
        if job is None:
            return
        try:
            job.log(self.format(record))
        except Exception:
            self.handleError(record)


_log_handler = JobLogHandler()
_log_handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))


def _ensure_log_handler():
    """Sanic/pytest dictConfig replaces root handlers and would drop JobLogHandler.

    Attach to this module's logger (not only root) so capture survives that reset.
    """
    for target in (logging.getLogger(), logger):
        if not any(isinstance(i, JobLogHandler) for i in target.handlers):
            target.addHandler(_log_handler)


_ensure_log_handler()


def _json_safe(value):
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


async def _run_job(job_id: str):
    """Run one Job to completion (or failure/cancellation) in this process."""
    _ensure_log_handler()
    record = _claim_job(job_id)
    if not record:
        # Cancelled while it was waiting in the queue.
        return

    name = record['name']
    context = JobContext(job_id, name)
    handler = JOB_HANDLERS.get(name)
    if handler is None:
        _update_job(job_id, status=FAILED, error=f'No handler is registered for {name!r}',
                    finished_at=now().isoformat())
        return

    token = _current_job.set(context)
    try:
        async def call():
            result = handler(**record['kwargs'])
            if inspect.isawaitable(result):
                result = await result
            return result

        # The task copies the current context, so the handler (and any tasks it creates) see this Job.
        task = asyncio.create_task(call())
        while not task.done():
            await asyncio.wait({task}, timeout=JOB_CANCEL_POLL_SECONDS)
            if not task.done() and _cancel_requested(job_id):
                task.cancel()
                try:
                    await task
                except BaseException:  # noqa Includes CancelledError; the Job is what was cancelled.
                    pass
                context.log('Cancelled')
                context.flush()
                _update_job(job_id, status=CANCELLED, finished_at=now().isoformat())
                logger.warning(f'Job {job_id} was cancelled')
                Events.send_user_notify(f'Cancelled: {record["description"]}')
                return

        try:
            result = task.result()
        except asyncio.CancelledError:
            # The worker itself is shutting down; leave the record honest.
            _update_job(job_id, status=CANCELLED, finished_at=now().isoformat())
            raise
        except Exception as e:
            logger.error(f'Job {job_id} failed', exc_info=e)
            # Do not rely on JobLogHandler for this line: Sanic/pytest dictConfig can
            # strip root handlers (especially under xdist on CI), so the traceback
            # never reaches the Job log even though `error` is set.
            context.log(f'{type(e).__name__}: {e}')
            context.flush()
            _update_job(job_id, status=FAILED, error=str(e) or repr(e),
                        log=list(context._log), finished_at=now().isoformat())
            Events.send_user_notify(f'Failed: {record["description"]}')
            return

        context.flush()
        _update_job(job_id, status=COMPLETE, result=_json_safe(result), progress=100.0,
                    finished_at=now().isoformat())
        logger.info(f'Job {job_id} completed')
        Events.send_user_notify(f'Completed: {record["description"]}')
    finally:
        context.flush()
        _current_job.reset(token)


async def process_job_queue() -> int:
    """Run every queued Job, in order.  Returns how many were run."""
    count = 0
    while True:
        try:
            job_id = _queue().get_nowait()
        except queue.Empty:
            return count
        count += 1
        await _run_job(job_id)


@perpetual_signal(sleep=0.5)
async def job_worker():
    """The single consumer of the Job queue; runs in the perpetual process only."""
    try:
        job_id = _queue().get_nowait()
    except queue.Empty:
        return
    await _run_job(job_id)


async def wait_for_job(job_id: str, timeout: float = 300) -> dict:
    """Wait for a Job to finish; returns its record.

    In tests (no perpetual loop) the queue is drained by this waiter so the Job actually runs.

    @raise TimeoutError: when the Job has not finished in time.
    """
    start = time.time()
    while time.time() - start < timeout:
        record = get_job(job_id)
        if record['status'] in FINISHED_STATUSES:
            return record
        if PYTEST:
            await process_job_queue()
        await asyncio.sleep(0.01 if PYTEST else 0.5)
    raise TimeoutError(f'Job {job_id} did not finish in time')


jobs_bp = Blueprint('Jobs', url_prefix='/api/jobs')


@jobs_bp.get('/')
@openapi.description('List all Jobs, oldest first.  Jobs are not saved; an API restart forgets them.')
async def get_jobs_request(_: Request):
    return json_response({'jobs': get_jobs()})


@jobs_bp.get('/<job_id:str>')
@openapi.description('Get one Job, including its log tail.')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def get_job_request(_: Request, job_id: str):
    return json_response({'job': get_job(job_id)})


@jobs_bp.delete('/<job_id:str>')
@openapi.description('Cancel a pending or running Job.  Allowed in WROL Mode: it only stops work.')
@openapi.response(HTTPStatus.NOT_FOUND, JSONErrorResponse)
async def cancel_job_request(_: Request, job_id: str):
    return json_response({'job': cancel_job(job_id)})
