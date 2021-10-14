#! /usr/bin/env python3
import argparse
import asyncio
import inspect
import logging
import sys

import pytz

from wrolpi import root_api, BEFORE_STARTUP_FUNCTIONS
from wrolpi.common import logger, get_config, set_timezone
from wrolpi.vars import PROJECT_DIR, MODULES_DIR

logger = logger.getChild('wrolpi-main')


def db_main(args):
    """
    Handle database migrations.  Currently this uses Alembic, supported commands are "upgrade" and "downgrade".
    """
    from alembic.config import Config
    from alembic import command
    from wrolpi.db import uri

    config = Config(PROJECT_DIR / 'alembic.ini')
    # Overwrite the Alembic config, the is usually necessary when running in a docker container.
    config.set_main_option('sqlalchemy.url', uri)

    logger.warning(f'DB URI: {uri}')

    if args.command == 'upgrade':
        command.upgrade(config, 'head')
    elif args.command == 'downgrade':
        command.downgrade(config, '-1')
    else:
        print(f'Unknown DB command: {args.command}')
        return 2

    return 0


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='count')

    sub_commands = parser.add_subparsers(title='sub-commands', dest='sub_commands')

    # Add the API parser, this will allow the user to specify host/port etc.
    api_parser = sub_commands.add_parser('api')
    root_api.init_parser(api_parser)

    # DB Parser for running Alembic migrations
    db_parser = sub_commands.add_parser('db')
    db_parser.add_argument('command', help=f'Supported commands: upgrade, downgrade')

    args = parser.parse_args()
    logger.warning(f'Starting with: {sys.argv}')

    await set_log_level(args)

    # Run DB migrations before anything else.
    if args.sub_commands == 'db':
        return db_main(args)

    # Set the Timezone
    config = get_config()
    if 'timezone' in config:
        tz = pytz.timezone(config['timezone'])
        set_timezone(tz)

    # Import the API in every module.  Each API should attach itself to `root_api`.
    try:
        modules = [i.name for i in MODULES_DIR.iterdir() if i.is_dir() and not i.name.startswith('_')]
        for module in modules:
            module = f'modules.{module}.api'
            logger.debug(f'Importing {module}')
            __import__(module, globals(), locals(), [], 0)
    except ImportError as e:
        logger.fatal('No modules could be found!', exc_info=e)
        raise

    if not modules:
        raise Exception('No modules could be found!')

    # Run the startup functions
    for func in BEFORE_STARTUP_FUNCTIONS:
        try:
            logger.debug(f'Calling {func} before startup.')
            coro = func()
            if inspect.iscoroutine(coro):
                await coro
        except Exception as e:
            logger.warning(f'Startup {func} failed!', exc_info=e)

    # Run the API
    return root_api.main(args)


async def set_log_level(args):
    """
    Set the level at the root logger so all children that have been created (or will be created) share the same level.
    """
    root_logger = logging.getLogger()
    if args.verbose == 1:
        root_logger.setLevel(logging.INFO)
    elif args.verbose and args.verbose >= 2:
        root_logger.setLevel(logging.DEBUG)

    # Always warn about the log level so we know what will be logged
    effective_level = logger.getEffectiveLevel()
    level_name = logging.getLevelName(effective_level)
    logger.warning(f'Logging level: {level_name}')


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(main())
    sys.exit(result)
