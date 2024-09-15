#! /usr/bin/env python3
import argparse
import asyncio
import logging
import os
import sys

from sanic import Sanic
from sanic.signals import Event

from wrolpi import flags, BEFORE_STARTUP_FUNCTIONS, admin
from wrolpi import root_api  # noqa
from wrolpi import tags
from wrolpi.api_utils import api_app, perpetual_signal
from wrolpi.common import logger, check_media_directory, set_log_level, limit_concurrent, \
    cancel_refresh_tasks, cancel_background_tasks, get_wrolpi_config, can_connect_to_server, wrol_mode_enabled
from wrolpi.contexts import attach_shared_contexts, reset_shared_contexts, initialize_configs_contexts
from wrolpi.dates import Seconds
from wrolpi.downloader import import_downloads_config, download_manager
from wrolpi.vars import PROJECT_DIR, DOCKERIZED, INTERNET_SERVER
from wrolpi.version import get_version_string

logger = logger.getChild('wrolpi-main')


def db_main(args):
    """
    Handle database migrations.  This uses Alembic, supported commands are "upgrade" and "downgrade".
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

    videos = session.query(Video).all()
    videos = list(videos)
    for video in videos:
        get_video_duration(video.file_group.primary_path)

Check local variables:
locals().keys()

'''


def launch_interactive_shell():
    """Launches an interactive shell with a DB session."""
    import code
    from wrolpi.db import get_db_session

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

    if not args.sub_commands:
        parser.print_help()
        return 1

    logger.warning(f'Starting with: {sys.argv}')
    if args.verbose == 1:
        set_log_level(logging.INFO)
    elif args.verbose and args.verbose == 2:
        set_log_level(logging.DEBUG)
    elif args.verbose and args.verbose >= 3:
        # Log everything.  Add SQLAlchemy debug logging.
        set_log_level(logging.NOTSET)
    logger.info(get_version_string())

    if DOCKERIZED:
        logger.info('Running in Docker')

    check_media_directory()

    # Run DB migrations before anything else.
    if args.sub_commands == 'db':
        return db_main(args)

    # Run the API.
    if args.sub_commands == 'api':
        return root_api.main(args)

    return 1


@api_app.main_process_ready
async def startup(app: Sanic):
    """
    Initializes multiprocessing tools, flags, etc.

    Performed only once when the server starts, this is done before server processes are forked.

    @warning: This is NOT run after auto-reload!  You must stop and start Sanic.
    """
    logger.debug('startup')

    check_media_directory()

    if ('api',) not in app.router.routes_all:
        logger.debug(f'{app.router.routes_all=}')
        raise RuntimeError('WROLPi routes do not exist!  Was root_api imported?')

    # Initialize multiprocessing shared contexts before forking Sanic processes.
    attach_shared_contexts(app)
    logger.debug('startup done')


@api_app.listener('after_server_start')  # FileConfigs need to be initialized first.
async def initialize_configs(app: Sanic):
    """Each Sanic process runs this once."""
    # Each process will have their own FileConfig object, but share the `app.shared_ctx.*config`
    logger.debug('initialize_configs')

    try:
        initialize_configs_contexts(app)
        await asyncio.sleep(0.5)
        wrol_mode_enabled()
        logger.info(f'initialize_configs succeeded pid={os.getpid()}')
    except Exception as e:
        logger.error('initialize_configs failed with', exc_info=e)
        raise


@api_app.signal(Event.SERVER_SHUTDOWN_BEFORE)
@api_app.listener('reload_process_stop')
@limit_concurrent(1)
async def handle_server_shutdown(*args, **kwargs):
    """Stop downloads when server is shutting down."""
    logger.warning('Shutting down')
    download_manager.stop()
    await cancel_refresh_tasks()
    await cancel_background_tasks()


@api_app.signal(Event.SERVER_SHUTDOWN_AFTER)
async def handle_server_shutdown_reset(app: Sanic, loop):
    """Reset things after shutdown is complete, just in case server is going to start again."""
    reset_shared_contexts(app)


# Start periodic tasks after configs are ready.
@api_app.after_server_start
async def start_single_tasks(app: Sanic):
    """Recurring/Single tasks that are started in only one Sanic process."""
    # Only allow one child process to perform periodic tasks.  See `handle_server_shutdown`
    if app.shared_ctx.single_tasks_started.is_set():
        return
    app.shared_ctx.single_tasks_started.set()

    from modules.zim.lib import flag_outdated_zim_files

    logger.debug(f'start_single_tasks started')
    if get_wrolpi_config().download_on_startup:
        download_manager.enable()
    else:
        download_manager.disable()

    try:
        flag_outdated_zim_files()
    except Exception as e:
        logger.error('Failed to flag outdated Zims', exc_info=e)

    logger.debug('start_single_tasks waiting for db...')
    async with flags.db_up.wait_for():
        logger.debug('start_single_tasks db is up')

    tags.import_tags_config()

    await import_downloads_config()

    if flags.refresh_complete.is_set():
        # Set all downloads to new.
        download_manager.retry_downloads()

    # Hotspot/throttle are not supported in Docker containers.
    if not DOCKERIZED:
        if get_wrolpi_config().hotspot_on_startup:
            logger.info('Starting hotspot...')
            try:
                admin.enable_hotspot()
            except Exception as e:
                logger.error('Failed to enable hotspot', exc_info=e)
        else:
            logger.info('Hotspot on startup is disabled.')

        if get_wrolpi_config().throttle_on_startup:
            logger.info('Throttling CPU...')
            try:
                admin.throttle_cpu_on()
            except Exception as e:
                logger.error('Failed to throttle CPU', exc_info=e)
        else:
            logger.info('CPU throttle on startup is disabled')

    # Run the startup functions
    for func in BEFORE_STARTUP_FUNCTIONS:
        try:
            logger.debug(f'Calling {func} before startup.')
            func()
        except Exception as e:
            logger.warning(f'Startup {func} failed!', exc_info=e)

    logger.debug(f'start_single_tasks done')


@perpetual_signal(sleep=1)
async def periodic_check_log_level():
    """Copies global log level into this Sanic worker's logger."""
    log_level = api_app.shared_ctx.log_level.value
    if log_level != logger.getEffectiveLevel():
        logger.info(f'changing log level from {logger.getEffectiveLevel()} to {log_level}')
        set_log_level(log_level, warn_level=False)


@perpetual_signal(sleep=10)
async def perpetual_check_db_is_up_worker():
    try:
        flags.check_db_is_up()
        flags.init_flags()
    except Exception as e:
        logger.error('Failed to check db status', exc_info=e)


@perpetual_signal(sleep=10)
async def perpetual_have_internet_worker():
    try:
        if can_connect_to_server(INTERNET_SERVER):
            flags.have_internet.set()
            # Check hourly once we have internet.
            await asyncio.sleep(float(Seconds.hour))
        else:
            # Check more often until the internet is back.
            flags.have_internet.clear()
    except Exception as e:
        logger.error('Failed to check if internet is up', exc_info=e)


@perpetual_signal(sleep=30)
async def periodic_start_video_missing_comments_download():
    from modules.videos.video.lib import get_missing_videos_comments

    async with flags.refresh_complete.wait_for():
        # We can't search for Videos missing comments until the refresh has completed.
        pass

    # Wait for download manager to startup.
    await asyncio.sleep(5)

    # Fetch comments for videos every hour.
    if download_manager.is_disabled or download_manager.is_stopped:
        logger.debug('Waiting for downloads to be enabled before downloading comments...')
        await asyncio.sleep(10)
    elif not flags.have_internet.is_set():
        logger.debug('Waiting for internet before downloading comments...')
        await asyncio.sleep(30)
    else:
        try:
            await get_missing_videos_comments()
        except Exception as e:
            logger.error('Failed to get missing video comments', exc_info=e)

        await asyncio.sleep(int(Seconds.hour))


if __name__ == '__main__':
    sys.exit(main())
