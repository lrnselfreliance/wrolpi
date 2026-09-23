import asyncio
import json
import logging
import os
from datetime import datetime, timezone, date
from decimal import Decimal
from functools import wraps
from http import HTTPStatus
from pathlib import Path

from sanic import response, HTTPResponse, Request, Sanic, SanicException

from wrolpi.common import Base, get_media_directory, logger, LOGGING_CONFIG
from wrolpi.errors import APIError
from wrolpi.perpetual import PERPETUAL_LOOPS, PER_WORKER_TASKS, PerpetualLoop, run_loop
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


def perpetual_signal(sleep: int | float = 1, run_while_testing: bool = False):
    """Register a singleton background loop.  The wrapped function is called forever, `sleep` seconds after each
    call returns, in the ONE perpetual process that Sanic's Worker Manager owns (see wrolpi/perpetual.py).  Errors
    are logged and the loop continues; a long call is not re-entered until it returns.

    The function is returned unchanged so tests can call it directly.  Under pytest nothing is registered unless
    `run_while_testing` is set."""

    def wrapper(func: callable):
        if PYTEST and not run_while_testing:
            return func
        PERPETUAL_LOOPS.append(PerpetualLoop(func.__name__, func, sleep))
        return func

    return wrapper


def per_worker_task(sleep: int | float = 1):
    """Register a loop that EVERY Sanic server worker runs for itself (e.g. syncing its own log level).  Anything
    that must happen exactly once belongs in `perpetual_signal` instead."""

    def wrapper(func: callable):
        if PYTEST:
            return func
        PER_WORKER_TASKS.append(PerpetualLoop(func.__name__, func, sleep))
        return func

    return wrapper


@api_app.after_server_start
async def start_per_worker_tasks(app: Sanic):
    stop = asyncio.Event()
    app.ctx.per_worker_stop = stop
    app.ctx.per_worker_tasks = [asyncio.create_task(run_loop(loop, stop), name=loop.name) for loop in PER_WORKER_TASKS]
    logger.info(f'start_per_worker_tasks pid={os.getpid()} tasks={[i.name for i in PER_WORKER_TASKS]}')


@api_app.listener('before_server_stop')
async def stop_per_worker_tasks(app: Sanic):
    stop = getattr(app.ctx, 'per_worker_stop', None)
    if stop is not None:
        stop.set()
    tasks = getattr(app.ctx, 'per_worker_tasks', None) or []
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
