"""WROLPi's background loops.

Singleton loops (file worker, downloads, switches, jobs, bulk tag, flag checks, update check)
run in ONE process that Sanic's Worker Manager owns: `run_perpetual_process` is handed to
`app.manager.manage()` from `main_process_ready`.  The manager guarantees a single instance and
signals it to stop (SIGINT on shutdown, SIGTERM when it is restarted); a Sanic server worker never
runs these loops, so there is nothing for a worker to claim, hand off, or take over.

If the process dies (an OOM kill on a small Pi is the realistic case), the manager only marks it
FAILED.  Every server worker runs `perpetual_process_health_check`, which asks the manager to
restart it; the new process reconciles shared state left behind by its predecessor
(`reconcile_after_predecessor`) before starting its loops.

Per-worker loops (things every Sanic server process must do for itself, like syncing its log
level) run as asyncio tasks inside each server worker.

Both kinds are registered at import time with the decorators in `wrolpi.api_utils`
(`perpetual_signal` and `per_worker_task`) and are no-ops under pytest; tests call the loop
bodies directly.
"""
import asyncio
import os
import signal
import time
from asyncio import CancelledError
from dataclasses import dataclass
from typing import Callable, Awaitable, Iterable

from wrolpi.common import logger

logger = logger.getChild(__name__)

PERPETUAL_PROCESS_NAME = 'Perpetual'
# Sanic names a managed process "-".join(["Sanic", name, index]) (sanic/worker/process.py).
PERPETUAL_PROCESS_IDENT = f'Sanic-{PERPETUAL_PROCESS_NAME}-0'
# A managed (non-server) process never reaches ACKED; these are the states the manager reports for one that
# is gone.  See sanic/worker/constants.py ProcessState.
PERPETUAL_PROCESS_DEAD_STATES = frozenset({'FAILED', 'COMPLETED', 'TERMINATED'})
# A restart request is idempotent to the manager, but five workers noticing one death should not log five times.
PERPETUAL_RESTART_COOLDOWN = 60
# How long the runner waits for cancelled loops before abandoning them at shutdown.
PERPETUAL_CANCEL_TIMEOUT = 15
# Shared multiprocessing locks whose critical sections are short.  A predecessor SIGKILLed inside one leaves it
# held forever and wedges every process that touches it; a live holder releases within this many seconds.
SHARED_LOCK_NAMES = ('jobs_lock', 'switches_lock', 'config_save_lock', 'config_update_lock', 'events_lock',
                     'secure_cookies_lock', 'transcode_lock')
SHARED_LOCK_HEAL_TIMEOUT = 10


@dataclass
class PerpetualLoop:
    name: str
    func: Callable[[], Awaitable]
    sleep: float


# Filled at import time by the decorators in wrolpi.api_utils.
PERPETUAL_LOOPS: list[PerpetualLoop] = []
PER_WORKER_TASKS: list[PerpetualLoop] = []


async def run_loop(loop: PerpetualLoop, stop: asyncio.Event):
    """Call `loop.func` forever, `loop.sleep` seconds after each call returns, until `stop` is set.

    An ordinary Exception is logged and the loop continues.  A long call is never re-entered: the next call
    starts only after the previous one returns.  Cancellation ends the loop; the runner is the only canceller.
    """
    while not stop.is_set():
        start = time.time()
        try:
            await loop.func()
        except CancelledError:
            raise
        except Exception as e:
            logger.error(f'Perpetual loop {loop.name} had error', exc_info=e)
        finally:
            logger.trace(f'Perpetual loop {loop.name} took {time.time() - start:.3f} seconds')

        try:
            await asyncio.wait_for(stop.wait(), timeout=loop.sleep)
        except asyncio.TimeoutError:
            pass


async def run_loops(loops: Iterable[PerpetualLoop], stop: asyncio.Event, cancel_timeout: float = PERPETUAL_CANCEL_TIMEOUT):
    """Run every loop as its own task until `stop` is set, then cancel them all and wait (bounded) for them to end."""
    tasks = [asyncio.create_task(run_loop(loop, stop), name=loop.name) for loop in loops]
    if not tasks:
        await stop.wait()
        return

    await stop.wait()
    for task in tasks:
        task.cancel()
    done, pending = await asyncio.wait(tasks, timeout=cancel_timeout)
    for task in pending:
        logger.warning(f'Perpetual loop {task.get_name()} did not stop within {cancel_timeout}s; abandoning it')
    for task in done:
        if not task.cancelled() and task.exception():
            logger.error(f'Perpetual loop {task.get_name()} ended with error', exc_info=task.exception())


def install_stop_signal_handlers(loop: asyncio.AbstractEventLoop, stop: asyncio.Event):
    """SIGINT (the manager's shutdown) and SIGTERM (the manager restarting us) set `stop`; a second signal is
    ignored rather than killing us mid-cleanup."""
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)


async def _shutdown_singletons():
    """Stop the singleton services that live in this process before its loops are cancelled."""
    from wrolpi.common import cancel_refresh_tasks, cancel_background_tasks
    from wrolpi.downloader import download_manager

    try:
        download_manager.stop()
    except Exception as e:
        logger.error('download_manager.stop failed during perpetual shutdown', exc_info=e)
    try:
        await cancel_refresh_tasks()
    except Exception as e:
        logger.error('cancel_refresh_tasks failed during perpetual shutdown', exc_info=e)
    try:
        await cancel_background_tasks()
    except Exception as e:
        logger.error('cancel_background_tasks failed during perpetual shutdown', exc_info=e)


def heal_shared_locks(app, timeout: float = SHARED_LOCK_HEAL_TIMEOUT) -> list[str]:
    """Release any shared lock still held after `timeout` seconds; returns the names released.

    Only this process's predecessor can have held one for that long (the sections are short), and it is dead.
    `multiprocessing.Lock` is a semaphore, so any process may release it."""
    healed = []
    for name in SHARED_LOCK_NAMES:
        lock = getattr(app.shared_ctx, name, None)
        if lock is None:
            continue
        if lock.acquire(timeout=timeout):
            lock.release()
            continue
        logger.warning(f'Shared lock {name} was held by a dead process; releasing it')
        try:
            lock.release()
        except ValueError:
            # Released by its holder between our two calls.
            pass
        healed.append(name)
    return healed


def reconcile_after_predecessor(app) -> dict:
    """Undo what a perpetual process that died mid-work left in shared state and the DB.

    Shared state outlives the process: a domain still in `processing_domains` would never download again, a
    `pending` Download or a RUNNING Job would stay that way forever, and the file-worker status would show a
    refresh that is not happening.  On a first start all of this is already clean, so this is idempotent.
    Each step is independent; one failing (e.g. no database yet) must not stop the others.
    """
    from wrolpi.downloader import download_manager, Download, DownloadStatus
    from wrolpi.files.worker import file_worker
    from wrolpi.jobs import fail_orphaned_jobs
    from wrolpi.db import get_db_session

    report = dict(locks=[], jobs=0, downloads=0, processing_domains=0, file_worker_jobs=0)

    report['locks'] = heal_shared_locks(app)

    try:
        report['jobs'] = fail_orphaned_jobs()
    except Exception as e:
        logger.error('reconcile: failed to fail orphaned Jobs', exc_info=e)

    try:
        domains = list(download_manager.processing_domains) if 'processing_domains' in \
            app.shared_ctx.download_manager_data else []
        if domains:
            logger.warning(f'reconcile: clearing processing_domains left by a dead process: {domains}')
            download_manager.processing_domains = []
        report['processing_domains'] = len(domains)
    except Exception as e:
        logger.error('reconcile: failed to clear processing_domains', exc_info=e)

    try:
        with get_db_session(commit=True) as session:
            report['downloads'] = session.query(Download) \
                .filter(Download.status == DownloadStatus.pending) \
                .update(dict(status=DownloadStatus.new), synchronize_session=False)
        if report['downloads']:
            logger.warning(f'reconcile: renewed {report["downloads"]} pending Download(s) left by a dead process')
    except Exception as e:
        # No database yet (media not mounted) is normal at boot; perpetual_check_db_is_up_worker handles it.
        logger.debug('reconcile: could not renew pending Downloads', exc_info=e)

    try:
        for job_id, record in list(file_worker._jobs.items()):
            status = record['status'] if isinstance(record, dict) else record
            if status == 'running':
                file_worker._set_job_status(job_id, 'failed', 'The file worker process exited before it finished')
                report['file_worker_jobs'] += 1
        if report['file_worker_jobs'] or (file_worker.status and file_worker.status.get('status') != 'idle'):
            file_worker.reset_status()
    except Exception as e:
        logger.error('reconcile: failed to reset the file worker status', exc_info=e)

    if any(report.values()):
        logger.warning(f'reconcile_after_predecessor: {report}')
    return report


def _initialize_process():
    """What Sanic's `after_server_start` listeners do for a server worker, done here for this process: each
    process owns its FileConfig objects (they share `shared_ctx.*config`).  Then clean up after a predecessor."""
    from wrolpi.api_utils import api_app
    from wrolpi.contexts import initialize_configs_contexts

    initialize_configs_contexts(api_app)
    reconcile_after_predecessor(api_app)


async def serve_perpetual_loops(loops: Iterable[PerpetualLoop], stop: asyncio.Event | None = None,
                                initialize: Callable[[], None] = _initialize_process):
    """The perpetual process's main coroutine."""
    stop = stop or asyncio.Event()
    install_stop_signal_handlers(asyncio.get_running_loop(), stop)
    initialize()
    loops = list(loops)
    logger.info(f'Perpetual process started pid={os.getpid()} loops={[i.name for i in loops]}')
    runner = asyncio.create_task(run_loops(loops, stop), name='perpetual-runner')
    await stop.wait()
    logger.warning('Perpetual process stopping')
    await _shutdown_singletons()
    await runner
    logger.info('Perpetual process stopped')


def run_perpetual_process():
    """Entry point handed to `app.manager.manage()`.  Runs in its own (forked) process: it inherits `api_app`,
    the populated `shared_ctx`, and the module singletons, and needs no arguments."""
    # The fork inherited the manager's Python signal handlers; until the event loop installs ours, a signal
    # must do the default thing (exit) rather than run the manager's handler inside this process.
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    if not PERPETUAL_LOOPS:
        # Only `fork` carries the import-time registrations into this process; under `spawn` nothing would run.
        raise RuntimeError('No perpetual loops are registered in this process; is Sanic.start_method "fork"?')
    asyncio.run(serve_perpetual_loops(PERPETUAL_LOOPS))


def register_perpetual_process(app) -> None:
    """Called from `main_process_ready` after `shared_ctx` is attached.  `transient=True` is load-bearing: it makes
    the manager restart the process on auto-reload and marks it restartable, which the health check's restart
    request requires."""
    app.manager.manage(PERPETUAL_PROCESS_NAME, run_perpetual_process, {}, transient=True)


def perpetual_process_needs_restart(workers: dict, now: float, last_request: float) -> bool:
    """True if the manager reports the perpetual process as gone and no restart was requested recently.

    `workers` is `app.m.workers` (a dict keyed by process name).  A missing entry is not "dead": the manager
    has not registered the process yet.
    """
    entry = workers.get(PERPETUAL_PROCESS_IDENT)
    if not entry or entry.get('state') not in PERPETUAL_PROCESS_DEAD_STATES:
        return False
    return (now - last_request) >= PERPETUAL_RESTART_COOLDOWN


def _claim_restart_request(app, workers: dict, now: float) -> bool:
    """Atomically decide, across all server workers, that this one issues the restart request.

    Two workers can read FAILED within the same monitor tick; a second `restart` would SIGTERM the process the
    first one just started.  The timestamp lives in `shared_ctx` under the Value's own lock."""
    requested_at = getattr(app.shared_ctx, 'perpetual_restart_requested_at', None)
    if requested_at is None:
        # Not attached (tests); fall back to a per-process cooldown.
        global _last_restart_request
        if not perpetual_process_needs_restart(workers, now, _last_restart_request):
            return False
        _last_restart_request = now
        return True
    with requested_at.get_lock():
        if not perpetual_process_needs_restart(workers, now, requested_at.value):
            return False
        requested_at.value = now
        return True


_last_restart_request = 0.0


async def perpetual_process_health_check():
    """Runs in every server worker: ask the manager to restart the perpetual process if it has died.

    Sanic only marks a dead managed process FAILED; it does not restart it.  This is a restart request to the
    manager, not a takeover: the loops still run in exactly one process.
    """
    from wrolpi.api_utils import api_app

    multiplexer = getattr(api_app, 'multiplexer', None)
    if multiplexer is None:
        return
    try:
        workers = multiplexer.workers
    except Exception as e:
        logger.debug('Could not read worker states', exc_info=e)
        return
    if not _claim_restart_request(api_app, workers, time.time()):
        return
    state = workers[PERPETUAL_PROCESS_IDENT].get('state')
    logger.warning(f'Perpetual process is {state}; requesting restart pid={os.getpid()}')
    multiplexer.restart(PERPETUAL_PROCESS_IDENT)
