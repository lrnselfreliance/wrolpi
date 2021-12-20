import inspect
from datetime import datetime
from functools import wraps
from uuid import UUID

import sanic
from sanic import response
from sanic_openapi import doc
from sanic_openapi.doc import Field

from wrolpi.common import string_to_boolean, logger
from wrolpi.errors import NoBodyContents, ValidationError, MissingRequiredField, ExcessJSONFields, API_ERRORS, APIError
from wrolpi.vars import DATE_FORMAT


def validate_data(model: type, data: dict):
    """
    Convert a JSON object to the model's specification.  If the JSON object matches the model's specification, this
    function will return a python dict of that data.  If it doesn't match, this will return a Sanic response object
    containing an error.
    """
    if not data:
        raise NoBodyContents()

    new_data = {}
    # Get the public attributes of the model
    attrs = [i for i in dir(model) if not str(i).startswith('__')]
    # Convert each json value to it's respective doc field's python type
    #  i.e. "json value" -> doc.String -> str
    missing_fields = []
    for attr in attrs:
        field = getattr(model, attr)
        try:
            if isinstance(field, doc.String):
                new_data[attr] = str(data.pop(attr))
            elif isinstance(field, doc.Integer):
                new_data[attr] = int(data.pop(attr))
            elif isinstance(field, doc.Tuple):
                new_data[attr] = tuple(data.pop(attr))
            elif isinstance(field, doc.UUID):
                new_data[attr] = UUID(data.pop(attr))
            elif isinstance(field, doc.Boolean):
                new_data[attr] = string_to_boolean(data.pop(attr))
            elif isinstance(field, doc.Float):
                val = data.pop(attr)
                new_data[attr] = float(val) if val else None
            elif isinstance(field, doc.Dictionary):
                new_data[attr] = dict(data.pop(attr))
            elif isinstance(field, doc.List):
                new_data[attr] = list(data.pop(attr))
            elif isinstance(field, Trinary):
                val = data.pop(attr)
                if val is not None:
                    val = string_to_boolean(val)
                new_data[attr] = val
            elif isinstance(field, doc.Date):
                val = data.pop(attr)
                if val:
                    new_data[attr] = datetime.strptime(val, DATE_FORMAT)
            elif isinstance(field, doc.DateTime):
                val = data.pop(attr)
                if val:
                    new_data[attr] = datetime.utcfromtimestamp(val)
            else:
                raise ValidationError(f'Bad field type {field} specified in the API model!')
        except KeyError:
            if field.required:
                missing_fields.append(attr)

    if missing_fields:
        raise MissingRequiredField(f'Missing fields: {missing_fields}')

    if data:
        raise ExcessJSONFields(f'Extra fields: {data.keys()}')

    return new_data


def validate_doc(summary: str = None, consumes=None, produces=None, responses=(), tag: str = None):
    """
    Apply Sanic OpenAPI docs to the wrapped route.  Perform simple validation on requests.
    """

    def wrapper(func):
        @wraps(func)
        async def wrapped(request, *a, **kw):
            try:
                if consumes:
                    if 'data' in kw:
                        raise OverflowError(f'data kwarg already being passed to {func}')

                    data = validate_data(consumes, request.json)
                    if isinstance(data, sanic.response.HTTPResponse):
                        # Error in validation
                        return data
                    kw['data'] = data

                result = func(request, *a, **kw)
                if inspect.iscoroutine(result):
                    result = await result
                return result
            except ValidationError as e:
                error = API_ERRORS[type(e)]
                body = {
                    'error': error['message'],
                    'code': error['code'],
                }
                logger.error(e, exc_info=True)

                if e.__cause__:
                    cause = e.__cause__
                    cause = API_ERRORS[type(cause)] if cause else None
                    body['cause'] = {'error': cause['message'], 'code': cause['code']}

                r = response.json(body, error['status'])
                return r
            except APIError as e:
                # The endpoint returned a standardized APIError, convert it to a json response
                error = API_ERRORS[type(e)]
                r = response.json({'message': str(e), 'api_error': error['message'], 'code': error['code']},
                                  error['status'])
                return r

        # Apply the docs to the wrapped function so sanic-openapi can find the wrapped function when
        # building the schema.  If these docs are applied to `func`, sanic-openapi won't be able to lookup `wrapped`
        if summary:
            wrapped = doc.summary(summary)(wrapped)
        if consumes:
            wrapped = doc.consumes(consumes, location='body')(wrapped)
        if produces:
            wrapped = doc.produces(produces)(wrapped)
        for resp in responses:
            wrapped = doc.response(*resp)(wrapped)
        if tag:
            wrapped = doc.tag(tag)(wrapped)

        return wrapped

    return wrapper


class SettingsObject:
    media_directory = doc.String()


class SettingsResponse:
    config = doc.Object(SettingsObject)


class SettingsRequest:
    media_directory = doc.String()
    wrol_mode = doc.Boolean()
    timezone = doc.String()


class RegexRequest:
    regex = doc.String()


class RegexResponse:
    regex = doc.String()
    valid = doc.Boolean()


class EchoResponse:
    form = doc.Dictionary()
    headers = doc.Dictionary()
    json = doc.String()
    method = doc.String()


class EventObject:
    name = doc.String()
    is_set = doc.Boolean()


class EventsResponse:
    events = doc.List(EventObject)


class DownloadRequest:
    urls = doc.String()


class Trinary(Field):
    """
    A field for API docs.  Can be True/False/None.
    """

    def __init__(self, *a, **kw):
        kw['choices'] = (True, False, None)
        super().__init__(*a, **kw)

    def serialize(self):
        return {"type": "trinary", **super().serialize()}


class JSONErrorResponse:
    error = doc.String()
