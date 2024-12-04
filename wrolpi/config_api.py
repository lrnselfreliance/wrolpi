from sanic import response, Blueprint
from sanic.request import Request
from sanic_ext.extensions.openapi import openapi

from wrolpi import config_schema
from wrolpi.api_utils import json_response
from wrolpi.common import get_all_configs, get_config_by_file_name
from wrolpi.common import logger
from wrolpi.errors import InvalidConfig

config_bp = Blueprint('config', '/api/config')


@config_bp.get('/')
@openapi.description('Get the status (imported, valid, etc.) of all configs.')
@openapi.parameter('file_name', str, location='query')
def get_config(request: Request):
    if file_name := request.args.get('file_name'):
        config = get_config_by_file_name(file_name)
        return json_response(dict(config=config))
    else:
        configs = get_all_configs()
        configs = {k: v.config_status() for k, v in configs.items()}
        return json_response(dict(configs=configs))


@config_bp.post('/')
@openapi.parameter('file_name', str, location='query')
@openapi.definition(
    description='Update the contents of a specific config.',
    body=config_schema.ConfigUpdateRequest,
    validate=True,
)
def post_config_update(request: Request, body: config_schema.ConfigUpdateRequest):
    file_name, = request.args['file_name']
    config = get_config_by_file_name(file_name)
    config.update(body.config)
    return response.empty()


@config_bp.post('/import')
@openapi.definition(
    description='Import the contents of a specific config.',
    body=config_schema.ConfigsRequest,
    validate=True,
)
def post_config_import(_: Request, body: config_schema.ConfigsRequest):
    config = get_config_by_file_name(body.file_name)
    try:
        config.import_config(send_events=True)
    except Exception as e:
        logger.error(f'Failed to import config: {body.file_name}', exc_info=e)
        raise InvalidConfig(f'Failed to import config {body.file_name}')

    return response.empty()


@config_bp.post('/dump')
@openapi.definition(
    description="Dump the contents of a specific config to it's file.",
    body=config_schema.ConfigsRequest,
    validate=True,
)
def post_config_dump(_: Request, body: config_schema.ConfigsRequest):
    config = get_config_by_file_name(body.file_name)
    try:
        config.dump_config(send_events=True, overwrite=body.overwrite)
    except Exception as e:
        logger.error(f'Failed to dump config: {body.file_name}', exc_info=e)
        raise InvalidConfig(f'Failed to dump config {body.file_name}')

    return response.empty()
