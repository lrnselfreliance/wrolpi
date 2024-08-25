import ctypes
import multiprocessing

from sanic import Sanic

default_log_level = 20


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
    app.shared_ctx.status = manager.dict()
    app.shared_ctx.map_importing = manager.dict()
    app.shared_ctx.switches = manager.dict()
    # Shared lists.
    app.shared_ctx.events_history = manager.list()
    app.shared_ctx.perpetual_workers = manager.list()
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
    app.shared_ctx.perpetual_tasks_started = multiprocessing.Event()

    # Warnings
    app.shared_ctx.warn_once = manager.dict()

    # Locks
    app.shared_ctx.config_save_lock = multiprocessing.Lock()
    app.shared_ctx.events_lock = multiprocessing.Lock()

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
    app.shared_ctx.status.clear()
    app.shared_ctx.status.update(dict(
        cpu_stats=dict(),
        load_stats=dict(),
        drives_stats=list(),
        processes_stats=list(),
        memory_stats=dict(),
    ))
    app.shared_ctx.map_importing.clear()
    app.shared_ctx.switches.clear()
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
    app.shared_ctx.perpetual_tasks_started.clear()

    # Lists
    del app.shared_ctx.events_history[:]
    del app.shared_ctx.perpetual_workers[:]


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
