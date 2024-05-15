import ctypes
import logging
import multiprocessing

from sanic import Sanic

from wrolpi.common import LOGGING_CONFIG

default_log_level = logging.getLevelName(LOGGING_CONFIG['root']['level'])


def attach_shared_contexts(app: Sanic):
    """Initializes Sanic's shared context with WROLPi's multiprocessing tools.

    This is called by main.py, and by testing."""
    manager = multiprocessing.Manager()

    # Many things wait for flags.db_up, initialize before starting.
    from wrolpi import flags

    app.shared_ctx.flags = manager.dict({i: False for i in flags.FLAG_NAMES})

    # ConfigFile multiprocessing_dict's.
    # Shared Configs
    app.shared_ctx.wrolpi_config = multiprocessing.Manager().dict()
    app.shared_ctx.tags_config = manager.dict()
    app.shared_ctx.inventories_config = manager.dict()
    app.shared_ctx.channels_config = manager.dict()
    app.shared_ctx.download_manager_config = manager.dict()
    app.shared_ctx.video_downloader_config = manager.dict()
    # Shared dicts.
    app.shared_ctx.refresh = manager.dict()
    app.shared_ctx.uploaded_files = manager.dict()
    app.shared_ctx.bandwidth = manager.dict()
    app.shared_ctx.disks_bandwidth = manager.dict()
    app.shared_ctx.max_disks_bandwidth = manager.dict()
    app.shared_ctx.map_importing = manager.dict()
    # Shared lists.
    app.shared_ctx.events_history = manager.list()
    # Shared ints
    app.shared_ctx.log_level = multiprocessing.Value(ctypes.c_int, default_log_level)

    # Download Manager
    app.shared_ctx.download_manager_data = manager.dict()
    app.shared_ctx.download_manager_queue = multiprocessing.Queue()
    app.shared_ctx.download_manager_disabled = multiprocessing.Event()
    app.shared_ctx.download_manager_stopped = multiprocessing.Event()

    # Events.
    app.shared_ctx.single_tasks_started = multiprocessing.Event()
    app.shared_ctx.flags_initialized = multiprocessing.Event()

    # Locks
    app.shared_ctx.config_save_lock = multiprocessing.Lock()

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
    app.shared_ctx.video_downloader_config.clear()
    # Shared dicts.
    app.shared_ctx.refresh.clear()
    app.shared_ctx.uploaded_files.clear()
    app.shared_ctx.bandwidth.clear()
    app.shared_ctx.disks_bandwidth.clear()
    app.shared_ctx.max_disks_bandwidth.clear()
    app.shared_ctx.map_importing.clear()
    # Shared ints
    app.shared_ctx.log_level.value = default_log_level

    # Download Manager
    app.shared_ctx.download_manager_data.clear()
    app.shared_ctx.download_manager_data.update(dict(
        processing_domains=[],
        killed_downloads=[],
    ))

    # Events.
    app.shared_ctx.single_tasks_started.clear()
    app.shared_ctx.download_manager_disabled.clear()
    app.shared_ctx.download_manager_stopped.clear()
    app.shared_ctx.flags_initialized.clear()


def initialize_configs_contexts(app: Sanic):
    """Assign multiprocessing Dicts to their respective FileConfigs in this process."""
    from modules.inventory.common import INVENTORIES_CONFIG
    from modules.videos.lib import CHANNELS_CONFIG
    from modules.videos.lib import VIDEO_DOWNLOADER_CONFIG
    from wrolpi.common import WROLPI_CONFIG
    from wrolpi.tags import TAGS_CONFIG
    from wrolpi.downloader import DOWNLOAD_MANAGER_CONFIG
    INVENTORIES_CONFIG.initialize(app.shared_ctx.inventories_config)
    CHANNELS_CONFIG.initialize(app.shared_ctx.channels_config)
    VIDEO_DOWNLOADER_CONFIG.initialize(app.shared_ctx.video_downloader_config)
    WROLPI_CONFIG.initialize(app.shared_ctx.wrolpi_config)
    TAGS_CONFIG.initialize(app.shared_ctx.tags_config)
    DOWNLOAD_MANAGER_CONFIG.initialize(app.shared_ctx.download_manager_config)
