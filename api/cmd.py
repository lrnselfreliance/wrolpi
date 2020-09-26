from pathlib import Path

from yoyo import get_backend
from yoyo import read_migrations

from api.common import logger
from api.db import get_db_args

logger = logger.getChild(__name__)


def apply_db_migrations(modules):
    """
    Apply all migrations in all modules.
    """
    db_args = get_db_args()
    dbname, user, password, host, port = \
        db_args['dbname'], db_args['user'], db_args['password'], db_args['host'], db_args['port']
    uri = f'postgres://{user}:{password}@{host}:{port}/{dbname}'
    backend = get_backend(uri)

    for module in modules.values():
        migrations = Path(module.__file__).parent / 'migrations'
        if not migrations.is_dir():
            continue

        migrations = read_migrations(str(migrations.absolute()))

        with backend.lock():
            # Get any outstanding migrations
            to_apply = backend.to_apply(migrations)
            # Apply them.
            backend.apply_migrations(to_apply)


def import_settings_configs(modules):
    logger.info('Importing configs')
    for module in modules.values():
        module.import_settings_config()
