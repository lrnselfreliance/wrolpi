from sanic import response, Blueprint
from sanic.request import Request
from sanic_ext.extensions.openapi import openapi

from wrolpi import config_schema
from wrolpi.api_utils import json_response
from wrolpi.common import get_all_configs, get_config_by_file_name, DB_CONFIG_FILE_NAMES
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


@config_bp.get('/backups')
@openapi.description('Get available backup dates for a config file.')
@openapi.parameter('file_name', str, location='query')
def get_config_backups(request: Request):
    file_name = request.args.get('file_name')
    if not file_name:
        raise InvalidConfig('file_name is required')
    config = get_config_by_file_name(file_name)
    if file_name not in DB_CONFIG_FILE_NAMES:
        raise InvalidConfig(f'{file_name} does not support backup import')
    dates = config.get_backup_dates()
    return json_response(dict(dates=dates))


@config_bp.post('/backup/preview')
@openapi.definition(
    description='Preview what a backup import would change.',
    body=config_schema.ConfigBackupPreviewRequest,
    validate=True,
)
def post_config_backup_preview(_: Request, body: config_schema.ConfigBackupPreviewRequest):
    if body.mode not in ('merge', 'overwrite'):
        raise InvalidConfig('mode must be "merge" or "overwrite"')
    config = get_config_by_file_name(body.file_name)
    if body.file_name not in DB_CONFIG_FILE_NAMES:
        raise InvalidConfig(f'{body.file_name} does not support backup import')
    backup_file = config._get_backup_file(body.backup_date)
    if not backup_file.is_file():
        raise InvalidConfig(f'Backup file not found for date {body.backup_date}')
    preview = config.preview_backup_import(body.backup_date, body.mode)
    return json_response(dict(preview=preview))


@config_bp.post('/backup/import')
@openapi.definition(
    description='Import a backup config file.',
    body=config_schema.ConfigBackupImportRequest,
    validate=True,
)
def post_config_backup_import(_: Request, body: config_schema.ConfigBackupImportRequest):
    if body.mode not in ('merge', 'overwrite'):
        raise InvalidConfig('mode must be "merge" or "overwrite"')
    config = get_config_by_file_name(body.file_name)
    if body.file_name not in DB_CONFIG_FILE_NAMES:
        raise InvalidConfig(f'{body.file_name} does not support backup import')
    backup_file = config._get_backup_file(body.backup_date)
    if not backup_file.is_file():
        raise InvalidConfig(f'Backup file not found for date {body.backup_date}')
    try:
        config.import_backup(body.backup_date, body.mode, send_events=True)
    except Exception as e:
        logger.error(f'Failed to import backup: {body.file_name} {body.backup_date}', exc_info=e)
        raise InvalidConfig(f'Failed to import backup {body.file_name}')

    return response.empty()
