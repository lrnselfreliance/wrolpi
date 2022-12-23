#! /usr/bin/env python3
import argparse
import logging
import sys

from sanic import Sanic
from sanic.signals import Event

from wrolpi import flags
from wrolpi import root_api, BEFORE_STARTUP_FUNCTIONS, admin
from wrolpi.common import logger, get_config, import_modules, check_media_directory, limit_concurrent, \
    wrol_mode_enabled, cancel_refresh_tasks
from wrolpi.downloader import download_manager, import_downloads_config
from wrolpi.events import Events
from wrolpi import flags
from wrolpi.root_api import api_app
from wrolpi.vars import PROJECT_DIR, DOCKERIZED, PYTEST
from wrolpi.version import get_version_string

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


INTERACTIVE_BANNER = '''
This is the interactive WROLPi shell.  Use this to interact with the WROLPi API library.

Example (get the duration of every video file):
from modules.videos.models import Video
from modules.videos.common import get_video_duration
videos = session.query(Video).filter(Video.video_path != None).all()
videos = list(videos)
for video in videos:
    get_video_duration(video.video_path.path)

Check local variables:
locals().keys()

'''


def launch_interactive_shell():
    """Launches an interactive shell with a DB session."""
    import code
    from wrolpi.db import get_db_session

    modules = import_modules()
    with get_db_session() as session:
        code.interact(banner=INTERACTIVE_BANNER, local=locals())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='count')
    parser.add_argument('--version', action='store_true', default=False)
    parser.add_argument('-c', '--check-media', action='store_true', default=False,
                        help='Check that the media directory is mounted and has the correct permissions.'
                        )
    parser.add_argument('-i', '--interactive', action='store_true', default=False,
                        help='Enter an interactive shell with some WROLPi tools')

    sub_commands = parser.add_subparsers(title='sub-commands', dest='sub_commands')

    # Add the API parser, this will allow the user to specify host/port etc.
    api_parser = sub_commands.add_parser('api')
    root_api.init_parser(api_parser)

    # DB Parser for running Alembic migrations
    db_parser = sub_commands.add_parser('db')
    db_parser.add_argument('command', help='Supported commands: upgrade, downgrade')

    args = parser.parse_args()

    if args.interactive:
        launch_interactive_shell()
        return 0

    if args.version:
        # Print out the relevant version information, then exit.
        print(get_version_string())
        return 0

    if args.check_media:
        # Run the media directory check.  Exit with informative return code.
        result = check_media_directory()
        if result is False:
            return 1
        print('Media directory is correct.')
        return 0

    logger.warning(f'Starting with: {sys.argv}')
    set_log_level(args)
    logger.debug(get_version_string())

    if DOCKERIZED:
        logger.info('Running in Docker')

    # Run DB migrations before anything else.
    if args.sub_commands == 'db':
        return db_main(args)

    config = get_config()

    # Hotspot/throttle are not supported in Docker containers.
    if not DOCKERIZED and config.hotspot_on_startup:
        admin.enable_hotspot()
    if not DOCKERIZED and config.throttle_on_startup:
        admin.throttle_cpu_on()

    check_media_directory()

    # Import the API in every module.  Each API should attach itself to `root_api`.
    import_modules()

    # Run the startup functions
    for func in BEFORE_STARTUP_FUNCTIONS:
        try:
            logger.debug(f'Calling {func} before startup.')
            func()
        except Exception as e:
            logger.warning(f'Startup {func} failed!', exc_info=e)

    # Run the API.
    return root_api.main(args)


def set_log_level(args):
    """
    Set the level at the root logger so all children that have been created (or will be created) share the same level.
    """
    root_logger = logging.getLogger()
    sa_logger = logging.getLogger('sqlalchemy.engine')
    if args.verbose == 1:
        root_logger.setLevel(logging.INFO)
    elif args.verbose and args.verbose == 2:
        root_logger.setLevel(logging.DEBUG)
    elif args.verbose and args.verbose >= 3:
        root_logger.setLevel(logging.DEBUG)
        sa_logger.setLevel(logging.DEBUG)

    # Always warn about the log level so we know what will be logged
    effective_level = logger.getEffectiveLevel()
    level_name = logging.getLevelName(effective_level)
    logger.warning(f'Logging level: {level_name}')


@api_app.before_server_start
async def startup(app: Sanic):
    flags.init_flags()
    await import_downloads_config()


@api_app.after_server_start
async def ready(app: Sanic):
    Events.send_ready()


@api_app.after_server_start
async def periodic_downloads(app: Sanic):
    """
    Starts the perpetual downloader on download manager.

    Limited to only one process.
    """
    if not flags.refresh_complete.is_set():
        logger.warning('Refusing to download without refresh')
        return

    # Set all downloads to new.
    download_manager.reset_downloads()

    if wrol_mode_enabled():
        logger.warning('Not starting download manager because WROL Mode is enabled.')
        download_manager.disable()
        return

    config = get_config()
    if config.download_on_startup is False:
        logger.warning('Not starting download manager because Downloads are disabled on startup.')
        download_manager.disable()
        return

    download_manager.enable()
    app.add_task(download_manager.perpetual_download())


@api_app.after_server_start
async def start_workers(app: Sanic):
    """All Sanic processes have their own Download workers."""
    if wrol_mode_enabled():
        logger.warning(f'Not starting download workers because WROL Mode is enabled.')
        download_manager.stop()
        return

    download_manager.start_workers()


@api_app.after_server_start
async def bandwidth_worker(app: Sanic):
    from wrolpi import status
    app.add_task(status.bandwidth_worker())


@root_api.api_app.signal(Event.SERVER_SHUTDOWN_BEFORE)
@limit_concurrent(1)
async def handle_server_shutdown(*args, **kwargs):
    """Stop downloads when server is shutting down."""
    if not PYTEST:
        download_manager.stop()
        await cancel_refresh_tasks()


if __name__ == '__main__':
    sys.exit(main())
