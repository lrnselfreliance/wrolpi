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
    # Reuse existing manager if available (avoids semaphore exhaustion in parallel tests).
    # Store on app.ctx (not shared_ctx) because Manager contains weakrefs that can't be pickled.
    if hasattr(app.ctx, 'manager') and app.ctx.manager is not None:
        reset_shared_contexts(app)
        return

    # Store manager reference for cleanup (important for tests to avoid semaphore leaks).
    # Must be on app.ctx, not shared_ctx, because Manager can't be pickled (contains weakrefs).
    app.ctx.manager = manager = multiprocessing.Manager()

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
    app.shared_ctx.domains_config = manager.dict()
    app.shared_ctx.archive_downloader_config = manager.dict()
    # Shared dicts.
    app.shared_ctx.refresh = manager.dict()
    app.shared_ctx.uploaded_files = manager.dict()
    app.shared_ctx.status = manager.dict()
    app.shared_ctx.map_importing = manager.dict()
    app.shared_ctx.cache = manager.dict()
    # Shared ints - keep as multiprocessing.Value because code uses get_lock()
    app.shared_ctx.log_level = multiprocessing.Value(ctypes.c_int, LOG_LEVEL_INT)

    # Download Manager
    app.shared_ctx.download_manager_data = manager.dict()
    # Use manager.Event() to avoid semaphore exhaustion in parallel tests
    app.shared_ctx.download_manager_disabled = manager.Event()
    app.shared_ctx.download_manager_stopped = manager.Event()
    # Downloads are only begun on startup using the wrolpi config's value. Do not start downloads before importing
    # config.
    app.shared_ctx.download_manager_disabled.set()
    app.shared_ctx.download_manager_stopped.set()

    # Use manager.Event() to avoid semaphore exhaustion in parallel tests
    app.shared_ctx.single_tasks_started = manager.Event()
    app.shared_ctx.flags_initialized = manager.Event()
    app.shared_ctx.perpetual_tasks_started = manager.Event()

    # Switches
    app.shared_ctx.switches = manager.dict()
    # Use manager.Lock/Event() to avoid semaphore exhaustion in parallel tests
    app.shared_ctx.switches_lock = manager.Lock()
    app.shared_ctx.switches_changed = manager.Event()
    # Use manager.Queue() because multiprocessing.Queue.qsize() raises NotImplementedError on macOS
    app.shared_ctx.archive_singlefiles = manager.Queue()
    app.shared_ctx.archive_screenshots = manager.Queue()

    # Bulk tagging
    app.shared_ctx.bulk_tag = manager.dict()
    # Use manager.Queue() because multiprocessing.Queue.qsize() raises NotImplementedError on macOS
    app.shared_ctx.bulk_tag_queue = manager.Queue()

    # FileWorker - cross-process job queue and progress tracking
    # Use manager.Queue() because multiprocessing.Queue.qsize() raises NotImplementedError on macOS
    app.shared_ctx.file_worker_queue = manager.Queue()
    app.shared_ctx.file_worker_data = manager.dict()
    # Use manager.Lock() to avoid semaphore exhaustion in parallel tests
    app.shared_ctx.file_worker_lock = manager.Lock()  # Ensure only one worker runs
    # Move operations progress tracking
    app.shared_ctx.move = manager.dict()

    # Warnings
    app.shared_ctx.warn_once = manager.dict()

    # Configs
    # Use manager.Lock() to avoid semaphore exhaustion in parallel tests
    app.shared_ctx.config_save_lock = manager.Lock()
    app.shared_ctx.config_update_lock = manager.Lock()
    app.shared_ctx.configs_imported = manager.dict()

    # Events.
    # Use manager.Lock() to avoid semaphore exhaustion in parallel tests
    app.shared_ctx.events_lock = manager.Lock()
    app.shared_ctx.events_history = manager.list()

    # Testing - controls whether Flag operations are active during tests.
    # Use manager.Event/Lock() to avoid semaphore exhaustion in parallel tests
    app.shared_ctx.testing_lock = manager.Event()
    app.shared_ctx.flags_lock = manager.Lock()

    reset_shared_contexts(app)


def reset_shared_contexts(app: Sanic):
    """Resets shared contexts (dicts/lists/Events,etc.).

    Should only be called when server is starting, or could start back up."""
    # Reset all flags to False
    from wrolpi import flags
    app.shared_ctx.flags.update({name: False for name in flags.FLAG_NAMES})

    # Should only be called when server is expected to start again.
    app.shared_ctx.wrolpi_config.clear()
    app.shared_ctx.tags_config.clear()
    app.shared_ctx.inventories_config.clear()
    app.shared_ctx.channels_config.clear()
    app.shared_ctx.download_manager_config.clear()
    app.shared_ctx.videos_downloader_config.clear()
    app.shared_ctx.domains_config.clear()
    app.shared_ctx.archive_downloader_config.clear()
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
        # Upgrade info defaults
        update_available=False,
        latest_commit=None,
        current_commit=None,
        commits_behind=0,
        git_branch=None,
    ))
    app.shared_ctx.map_importing.clear()
    app.shared_ctx.cache.clear()
    app.shared_ctx.move.clear()
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
    while True:
        # Clear out any pending screenshot generation switches.
        try:
            app.shared_ctx.archive_screenshots.get_nowait()
        except queue.Empty:
            break

    # Bulk tagging
    app.shared_ctx.bulk_tag.clear()
    app.shared_ctx.bulk_tag.update(dict(
        status='idle',  # 'idle', 'running'
        total=0,
        completed=0,
        add_tag_names=[],
        remove_tag_names=[],
        error=None,
    ))
    while True:
        # Clear out any pending bulk tag jobs.
        try:
            app.shared_ctx.bulk_tag_queue.get_nowait()
        except queue.Empty:
            break

    # FileWorker
    app.shared_ctx.file_worker_data.clear()
    app.shared_ctx.file_worker_data.update(dict(
        idempotency=None,
        counted_files=0,
        jobs={},
        move_jobs={},
        failed_items=[],  # List of serialized QueueItems for retry
        running=False,
    ))
    while True:
        # Clear out any pending file worker jobs.
        try:
            app.shared_ctx.file_worker_queue.get_nowait()
        except queue.Empty:
            break

    # Events.
    app.shared_ctx.single_tasks_started.clear()
    app.shared_ctx.flags_initialized.clear()
    app.shared_ctx.perpetual_tasks_started.clear()
    # Clear all accumulated events from the history (manager.list() doesn't have .clear())
    while len(app.shared_ctx.events_history) > 0:
        app.shared_ctx.events_history.pop()

    # Do not start downloads when reloading.
    app.shared_ctx.download_manager_stopped.set()
    app.shared_ctx.download_manager_disabled.set()

    # Testing - clear the testing lock on reset.
    app.shared_ctx.testing_lock.clear()


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

    try:
        from modules.archive.lib import domains_config
        domains_config.initialize(app.shared_ctx.domains_config)
    except Exception as e:
        logger.error(f'Failed to initialize in-memory domains config: {e}')

    try:
        from modules.archive.lib import ARCHIVE_DOWNLOADER_CONFIG
        ARCHIVE_DOWNLOADER_CONFIG.initialize(app.shared_ctx.archive_downloader_config)
    except Exception as e:
        logger.error(f'Failed to initialize in-memory archive downloader config: {e}')
