import asyncio
import json
import logging
import os
from asyncio import CancelledError
from datetime import datetime, timezone, date
from decimal import Decimal
from functools import wraps
from http import HTTPStatus
from pathlib import Path
from time import time

from sanic import response, HTTPResponse, Request, Sanic, SanicException

from wrolpi.common import Base, get_media_directory, logger, LOGGING_CONFIG, TRACE_LEVEL
from wrolpi.errors import APIError
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)

# Sanic 25.x wants to use 'spawn' as the multiprocessing start method, but our code
# uses 'fork' extensively (via multiprocessing.Manager, Event, Queue, etc.).
# Tell Sanic to use 'fork' and that the start method is already configured.
Sanic.start_method = "fork"
Sanic.START_METHOD_SET = True

# The only Sanic App, this is imported all over.
api_app = Sanic(name='api_app', log_config=LOGGING_CONFIG)


@wraps(response.json)
def json_response(*a, **kwargs) -> HTTPResponse:
    """
    Handles encoding date/datetime in JSON.
    """
    resp = response.json(*a, **kwargs, cls=CustomJSONEncoder, dumps=json.dumps)
    return resp


class CustomJSONEncoder(json.JSONEncoder):

    def default(self, obj):
        try:
            if hasattr(obj, '__json__'):
                # Get __json__ before others.
                return obj.__json__()
            elif isinstance(obj, datetime):
                # API always returns dates in UTC.
                if obj.tzinfo:
                    obj = obj.astimezone(timezone.utc)
                else:
                    # A datetime with no timezone is UTC.
                    obj = obj.replace(tzinfo=timezone.utc)
                obj = obj.isoformat()
                return obj
            elif isinstance(obj, date):
                # API always returns dates in UTC.
                obj = datetime(obj.year, obj.month, obj.day, tzinfo=timezone.utc)
                return obj.isoformat()
            elif isinstance(obj, Decimal):
                return str(obj)
            elif isinstance(obj, Base):
                if hasattr(obj, 'dict'):
                    return obj.dict()
            elif isinstance(obj, Path):
                media_directory = get_media_directory()
                try:
                    path = obj.relative_to(media_directory)
                except ValueError:
                    # Path may not be absolute.
                    path = obj
                if str(path) == '.':
                    return ''
                return str(path)
            return super(CustomJSONEncoder, self).default(obj)
        except Exception as e:
            logger.fatal(f'Failed to JSON encode {obj}', exc_info=e)
            raise


def get_error_json(exception: BaseException):
    """Return a JSON representation of the Exception instance."""
    if isinstance(exception, APIError):
        # An exception from WROLPi.
        body = dict(error=str(exception), message=exception.summary, code=exception.code)
    elif isinstance(exception, SanicException):
        # An exception from Sanic.
        body = dict(error=str(exception), message=exception.message, code=type(exception).__name__)
    else:
        # Not a WROLPi APIError error.
        body = dict(
            error=str(exception),
            message=None,
            code=type(exception).__name__,
        )
    if exception.__cause__:
        # This exception was caused by another, follow the stack.
        body['cause'] = get_error_json(exception.__cause__)
    return body


def json_error_handler(request: Request, exception: Exception):
    """Converts all API APIError/SanicException to more informative json object."""
    try:
        body = get_error_json(exception)
    except Exception as e:
        logger.error('Failed to create error json', exc_info=e)
        raise

    error = repr(str(body["error"]))
    message = repr(str(body["message"]))
    code = body['code']
    if logger.isEnabledFor(logging.DEBUG):
        logger.error(f'API returning JSON error {type(exception).__name__} {error=} {message=} {code=}',
                     exc_info=exception)
    else:
        logger.error(f'API returning JSON error {type(exception).__name__} {error=} {message=} {code=}')
    if isinstance(exception, SanicException):
        return json_response(body, exception.status_code)

    logger.error('Unexpected error', exc_info=exception)

    # Some unknown error, use internal error code.
    return json_response(body, HTTPStatus.INTERNAL_SERVER_ERROR)


api_app.error_handler.add(Exception, json_error_handler)


@api_app.middleware('request')
async def inject_session(request: Request):
    """Inject a database session into the request context.

    This session is deliberately *deferred*, even for a POST: it is committed by the response
    middleware, so a writer would hold the SQLite write lock for the whole handler -- including the
    slow parts (a chunk being written to disk, a subprocess) and including any background task the
    handler fires before returning.  A handler that writes should use `get_db_session(commit=True)`,
    which begins as a writer and commits before the handler returns.
    """
    from wrolpi.db import get_db_context
    engine, session = get_db_context()
    request.ctx.session = session
    request.ctx._db_engine = engine


@api_app.middleware('response')
async def cleanup_session(request: Request, response_: HTTPResponse):
    """Cleanup session after request completes."""
    if hasattr(request.ctx, 'session'):
        session = request.ctx.session
        try:
            if response_.status < 400:
                session.commit()
            else:
                session.rollback()
        except Exception:
            session.rollback()
            raise
        finally:
            # Don't close session during tests - the test_session fixture manages it.
            if not PYTEST:
                session.close()
    return response_


PERPETUAL_WORKERS = list()

FILE_WORKER_PERPETUAL_EVENT = 'wrolpi.perpetual.perpetual_file_worker_queue'
OWNER_WATCHDOG_EVENT = 'wrolpi.perpetual.perpetual_owner_watchdog'
OWNER_HEARTBEAT_STALE_SECONDS = 30


def _touch_heartbeat(app) -> None:
    try:
        app.shared_ctx.perpetual_tasks_heartbeat.value = time()
    except Exception:
        logger.error('Failed to update perpetual-tasks heartbeat', exc_info=True)


def _i_am_owner(app) -> bool:
    try:
        return app.shared_ctx.perpetual_tasks_owner_pid.value == os.getpid()
    except Exception:
        return False


def _perpetual_owner_is_alive(app) -> bool:
    """True if the claiming worker is still running *and* keeping a heartbeat.

    pid_is_running alone is not enough: after a crash the kernel can reuse the
    owner PID for an unrelated process.  A zero heartbeat means the owner just
    claimed and has not ticked yet, so a live PID still counts.
    """
    try:
        pid = app.shared_ctx.perpetual_tasks_owner_pid.value
    except Exception:
        return False
    if not pid:
        return False
    from wrolpi.cmd import pid_is_running
    if not pid_is_running(pid):
        return False
    try:
        heartbeat = app.shared_ctx.perpetual_tasks_heartbeat.value
    except Exception:
        return True
    if not heartbeat:
        return True
    return (time() - heartbeat) < OWNER_HEARTBEAT_STALE_SECONDS


def _claim_perpetual_tasks(app) -> bool:
    """Return True if this process should start the single-process perpetual loops.

    ``perpetual_tasks_started`` is a shared Event.  If the worker that set it
    exits (Sanic auto_reload in docker, crash), the Event stays set and every
    replacement ``after_server_start`` used to no-op — file processing, downloads,
    and switches stayed dead until a full API restart.  Track the owner PID and
    a heartbeat, and retake the claim when that process is gone or silent.
    """
    lock = getattr(app.shared_ctx, 'perpetual_tasks_lock', None)
    if lock is None:
        return _claim_perpetual_tasks_unlocked(app)
    with lock:
        return _claim_perpetual_tasks_unlocked(app)


def _claim_perpetual_tasks_unlocked(app) -> bool:
    if app.shared_ctx.perpetual_tasks_started.is_set() and _perpetual_owner_is_alive(app):
        return False
    app.shared_ctx.perpetual_tasks_started.set()
    try:
        app.shared_ctx.perpetual_tasks_owner_pid.value = os.getpid()
    except Exception:
        logger.error('Failed to record perpetual-tasks owner pid', exc_info=True)
    _touch_heartbeat(app)
    return True


def _perpetual_events_for_this_process(app) -> list[str]:
    """Events this worker should dispatch at startup.

    The claiming worker starts every perpetual loop (one file-worker consumer).
    Every other worker starts only the owner watchdog, which reclaims if the
    owner dies later — after_server_start will not run again on those processes.
    """
    if _claim_perpetual_tasks(app):
        events = list(PERPETUAL_WORKERS)
        if OWNER_WATCHDOG_EVENT not in events:
            events.append(OWNER_WATCHDOG_EVENT)
        return events
    return [OWNER_WATCHDOG_EVENT]


def _app_is_stopping() -> bool:
    """True when Sanic is shutting down (perpetual workers should not reschedule).

    Only the ``before_server_stop`` flag (and Sanic's ``is_stopping`` if it is
    ever set) count.  ``state.is_running`` stays False in some serving modes
    (including this project's docker Sanic workers), so treating
    ``is_started and not is_running`` as shutdown killed every perpetual
    worker after its first tick.
    """
    try:
        if getattr(api_app.ctx, 'perpetual_shutdown', False):
            return True
        state = getattr(api_app, 'state', None)
        return bool(state is not None and getattr(state, 'is_stopping', False))
    except Exception:
        return False


def _uncancel_current_task():
    """Allow a perpetual worker to continue after an unexpected CancelledError.

    Python 3.11+ re-raises CancelledError at the next await unless uncancel()
    is called.  Without this, catching CancelledError cannot reschedule.
    """
    task = asyncio.current_task()
    if task is not None and hasattr(task, 'uncancel'):
        task.uncancel()


@api_app.listener('before_server_start')
async def _clear_perpetual_shutdown(app):
    app.ctx.perpetual_shutdown = False


@api_app.listener('before_server_stop')
async def _set_perpetual_shutdown(app):
    app.ctx.perpetual_shutdown = True


async def _dispatch_perpetual(event_: str):
    """Dispatch a perpetual-signal event.  Isolated so tests can stub it."""
    await api_app.dispatch(event_)


@api_app.after_server_start
async def start_perpetual_tasks(app: Sanic):
    events = _perpetual_events_for_this_process(app)
    logger.info(f'start_perpetual_tasks started pid={os.getpid()} events={len(events)}')
    logger.debug(f'start_perpetual_tasks: {events}')

    try:
        for event_ in events:
            logger.debug(f'start_perpetual_tasks {event_}')
            await app.dispatch(event_)
    except Exception as e:
        logger.error('Failed to start perpetual tasks', exc_info=e)
        raise

    logger.debug('start_perpetual_tasks completed')


async def _run_perpetual_iteration(func: callable, event_: str, sleep: int | float):
    """Run one perpetual-worker iteration and reschedule unless shutting down.

    An ordinary Exception is logged and the loop continues.  CancelledError is
    terminal only during shutdown; any other cancellation is logged and the
    worker is rescheduled.  Previously any CancelledError skipped reschedule
    with no log, silently killing file processing for the life of the process.
    """
    logger.trace(f'perpetual_signal {event_}')
    start = time()
    try:
        await func()
    except CancelledError:
        if _app_is_stopping():
            logger.info(f'Perpetual worker {event_} cancelled during shutdown')
            raise
        logger.warning(
            f'Perpetual worker {event_} cancelled unexpectedly; will reschedule',
            exc_info=True,
        )
        _uncancel_current_task()
    except Exception as e:
        logger.error(f'Perpetual worker {event_} had error', exc_info=e)
    finally:
        if __debug__ and logger.isEnabledFor(TRACE_LEVEL):
            elapsed = int(time() - start)
            logger.trace(f'perpetual_signal {event_} took {elapsed} seconds')

    if PYTEST:
        return
    if _app_is_stopping():
        logger.info(f'Perpetual worker {event_} not rescheduling because the app is stopping')
        return

    try:
        await asyncio.sleep(sleep)
    except CancelledError:
        if _app_is_stopping():
            logger.info(f'Perpetual worker {event_} stopped during shutdown')
            raise
        logger.warning(
            f'Perpetual worker {event_} cancelled while sleeping; rescheduling immediately'
        )
        _uncancel_current_task()

    try:
        await _dispatch_perpetual(event_)
    except CancelledError:
        logger.info(f'Perpetual worker {event_} cancelled while dispatching next run')
        raise


def perpetual_signal(event: str = None, sleep: int | float = 1, run_while_testing: bool = False):
    """Use Sanic signals to continually call the wrapped function.  The wrapped function will continually be called,
    even if it has errors.  If the function is long-running, it will only be called again after it has finished."""

    def wrapper(func: callable):
        if PYTEST and not run_while_testing:
            # Do not run perpetual signal worker while testing, unless explicitly required.
            return func

        # Create a Sanic "signal" for the provided function.
        event_ = event or f'wrolpi.perpetual.{func.__name__}'

        # Wrap the function in a worker that will call it perpetually.
        @api_app.signal(event_)
        async def worker(*args, **kwargs):
            await _run_perpetual_iteration(lambda: func(*args, **kwargs), event_, sleep)

        # Add this new signal to the global list so that a task will be started after server startup.
        PERPETUAL_WORKERS.append(event_)
        return func

    return wrapper


async def perpetual_owner_watchdog():
    """Keep the owner heartbeat fresh, or reclaim the loops if the owner is gone.

    Non-owner Sanic workers run only this tick — not the file-worker pump — so
    file jobs stay single-consumer.  cancel_background_tasks / cancel_refresh_tasks
    do not cancel perpetual signals; the only intentional stop is shutdown.
    """
    if _app_is_stopping():
        return
    if _i_am_owner(api_app):
        _touch_heartbeat(api_app)
        return
    if not _claim_perpetual_tasks(api_app):
        return
    logger.warning(f'Perpetual-loop owner is gone; this worker is taking over pid={os.getpid()}')
    _touch_heartbeat(api_app)
    for event_ in list(PERPETUAL_WORKERS):
        if event_ == OWNER_WATCHDOG_EVENT:
            continue
        await _dispatch_perpetual(event_)


# Register after perpetual_signal is defined.  In PYTEST the decorator is a
# no-op, so tests call perpetual_owner_watchdog() directly.
perpetual_signal(sleep=5)(perpetual_owner_watchdog)
