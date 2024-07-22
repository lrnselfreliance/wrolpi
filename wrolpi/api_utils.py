import json
from datetime import datetime, timezone, date
from decimal import Decimal
from functools import wraps
from http import HTTPStatus
from pathlib import Path

from sanic import response, HTTPResponse, Request, Sanic, SanicException

from wrolpi.common import Base, get_media_directory, logger, LOGGING_CONFIG
from wrolpi.errors import APIError

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
        body = dict(error=str(exception), message=exception.message, code=exception.code)
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
    logger.error(f'API returning JSON error {type(exception).__name__} {error=} {message=} {code=}')
    if isinstance(exception, SanicException):
        return json_response(body, exception.status_code)

    logger.error('Unexpected error', exc_info=exception)

    # Some unknown error, use internal error code.
    return json_response(body, HTTPStatus.INTERNAL_SERVER_ERROR)
