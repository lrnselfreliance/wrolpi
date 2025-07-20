import asyncio
import json
import logging
import multiprocessing
import sys
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

PERPETUAL_WORKERS = list()


@api_app.after_server_start
async def start_perpetual_tasks(app: Sanic):
    # Only one set of perpetual tasks needs to be started.
    if app.shared_ctx.perpetual_tasks_started.is_set():
        return
    logger.info('start_perpetual_tasks started')
    logger.debug(f'start_perpetual_tasks: {PERPETUAL_WORKERS}')
    app.shared_ctx.perpetual_tasks_started.set()

    try:
        for event_ in PERPETUAL_WORKERS:
            logger.debug(f'start_perpetual_tasks {event_}')
            await app.dispatch(event_)
    except Exception as e:
        logger.error('Failed to start perpetual tasks', exc_info=e)
        raise

    logger.debug('start_perpetual_tasks completed')


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
            logger.trace(f'perpetual_signal {event_}')
            cancelled = False
            start = time()
            try:
                await func(*args, **kwargs)
            except CancelledError:
                cancelled = True
                raise
            except Exception as e:
                logger.error(f'Perpetual worker {event_} had error', exc_info=e)
            finally:
                if logger.isEnabledFor(TRACE_LEVEL):
                    elapsed = int(time() - start)
                    logger.trace(f'perpetual_signal {event_} took {elapsed} seconds')
                if not cancelled:
                    await asyncio.sleep(sleep)
                    await api_app.dispatch(event_)

        # Add this new signal to the global list so that a task will be started after server startup.
        PERPETUAL_WORKERS.append(event_)
        return func

    return wrapper
