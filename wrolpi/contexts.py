import ctypes
import multiprocessing
import queue

from sanic import Sanic

from wrolpi.common import logger
from wrolpi.vars import LOG_LEVEL_INT

logger = logger.getChild(__name__)


def attach_shared_contexts(app: Sanic):
    """Initializes Sanic's shared context with WROLPi's multiprocessing tools.

    This is called by main.py, and by testing."""
    manager = multiprocessing.Manager()

    # Many things wait for flags.db_up, initialize before starting.
    from wrolpi import flags

    app.shared_ctx.flags = manager.dict({i: False for i in flags.FLAG_NAMES})

    # ConfigFile multiprocessing_dict's.
    # Shared Configs
    app.shared_ctx.wrolpi_config = manager.dict()
    app.shared_ctx.tags_config = manager.dict()
    app.shared_ctx.inventories_config = manager.dict()
    app.shared_ctx.channels_config = manager.dict()
    app.shared_ctx.download_manager_config = manager.dict()
    app.shared_ctx.videos_downloader_config = manager.dict()
    # Shared dicts.
    app.shared_ctx.refresh = manager.dict()
    app.shared_ctx.uploaded_files = manager.dict()
    app.shared_ctx.status = manager.dict()
    app.shared_ctx.map_importing = manager.dict()
    app.shared_ctx.cache = manager.dict()
    # Shared ints
    app.shared_ctx.log_level = multiprocessing.Value(ctypes.c_int, LOG_LEVEL_INT)

    # Download Manager
    app.shared_ctx.download_manager_data = manager.dict()
    app.shared_ctx.download_manager_disabled = multiprocessing.Event()
    app.shared_ctx.download_manager_stopped = multiprocessing.Event()
    # Downloads are only begun on startup using the wrolpi config's value. Do not start downloads before importing
    # config.
    app.shared_ctx.download_manager_disabled.set()
    app.shared_ctx.download_manager_stopped.set()

    app.shared_ctx.single_tasks_started = multiprocessing.Event()
    app.shared_ctx.flags_initialized = multiprocessing.Event()
    app.shared_ctx.perpetual_tasks_started = multiprocessing.Event()

    # Switches
    app.shared_ctx.switches = manager.dict()
    app.shared_ctx.switches_lock = multiprocessing.Lock()
    app.shared_ctx.switches_changed = multiprocessing.Event()
    app.shared_ctx.archive_singlefiles = multiprocessing.Queue()

    # Warnings
    app.shared_ctx.warn_once = manager.dict()

    # Configs
    app.shared_ctx.config_save_lock = multiprocessing.Lock()
    app.shared_ctx.config_update_lock = multiprocessing.Lock()
    app.shared_ctx.configs_imported = manager.dict()

    # Events.
    app.shared_ctx.events_lock = multiprocessing.Lock()
    app.shared_ctx.events_history = manager.list()

    reset_shared_contexts(app)


def reset_shared_contexts(app: Sanic):
    """Resets shared contexts (dicts/lists/Events,etc.).

    Should only be called when server is starting, or could start back up."""
    # Should only be called when server is expected to start again.
    app.shared_ctx.wrolpi_config.clear()
    app.shared_ctx.tags_config.clear()
    app.shared_ctx.inventories_config.clear()
    app.shared_ctx.channels_config.clear()
    app.shared_ctx.download_manager_config.clear()
    app.shared_ctx.videos_downloader_config.clear()
    # Shared dicts.
    app.shared_ctx.refresh.clear()
    app.shared_ctx.uploaded_files.clear()
    app.shared_ctx.status.clear()
    app.shared_ctx.status.update(dict(
        cpu_stats=dict(),
        load_stats=dict(),
        drives_stats=list(),
        processes_stats=list(),
        memory_stats=dict(),
    ))
    app.shared_ctx.map_importing.clear()
    app.shared_ctx.cache.clear()
    # Shared ints
    app.shared_ctx.log_level.value = LOG_LEVEL_INT

    # Download Manager
    app.shared_ctx.download_manager_data.clear()
    app.shared_ctx.download_manager_data.update(dict(
        processing_domains=[],
        killed_downloads=[],
    ))

    # Configs
    app.shared_ctx.configs_imported.clear()

    # Switches
    app.shared_ctx.switches.clear()
    app.shared_ctx.switches_changed.clear()
    while True:
        # Clear out any pending singlefile archive switches.
        try:
            app.shared_ctx.archive_singlefiles.get_nowait()
        except queue.Empty:
            break

    # Events.
    app.shared_ctx.single_tasks_started.clear()
    app.shared_ctx.flags_initialized.clear()
    app.shared_ctx.perpetual_tasks_started.clear()

    # Do not start downloads when reloading.
    app.shared_ctx.download_manager_stopped.set()
    app.shared_ctx.download_manager_disabled.set()


def initialize_configs_contexts(app: Sanic):
    """Assign multiprocessing Dicts to their respective FileConfigs in this process."""
    from modules.inventory.common import INVENTORIES_CONFIG
    from modules.videos.lib import CHANNELS_CONFIG
    from modules.videos.lib import VIDEOS_DOWNLOADER_CONFIG
    from wrolpi.common import WROLPI_CONFIG
    from wrolpi.tags import TAGS_CONFIG
    from wrolpi.downloader import DOWNLOAD_MANAGER_CONFIG

    try:  # noqa
        INVENTORIES_CONFIG.initialize(app.shared_ctx.inventories_config)
    except Exception as e:
        logger.error(f'Failed to initialize in-memory inventories config: {e}')

    try:
        CHANNELS_CONFIG.initialize(app.shared_ctx.channels_config)
    except Exception as e:
        logger.error(f'Failed to initialize in-memory channels config: {e}')

    try:
        VIDEOS_DOWNLOADER_CONFIG.initialize(app.shared_ctx.videos_downloader_config)
    except Exception as e:
        logger.error(f'Failed to initialize in-memory videos downloader config: {e}')

    try:  # noqa
        WROLPI_CONFIG.initialize(app.shared_ctx.wrolpi_config)
    except Exception as e:
        logger.error(f'Failed to initialize in-memory wrolpi config config: {e}')

    try:
        TAGS_CONFIG.initialize(app.shared_ctx.tags_config)
    except Exception as e:
        logger.error(f'Failed to initialize in-memory tags config: {e}')

    try:
        DOWNLOAD_MANAGER_CONFIG.initialize(app.shared_ctx.download_manager_config)
    except Exception as e:
        logger.error(f'Failed to initialize in-memory download manager config: {e}')
