"""WROLPi's background loops.

Singleton loops (file worker, downloads, switches, jobs, bulk tag, flag checks, update check)
run in ONE process that Sanic's Worker Manager owns: `run_perpetual_process` is handed to
`app.manager.manage()` from `main_process_ready`.  The manager guarantees a single instance and
sends it SIGTERM on shutdown; a Sanic server worker never runs these loops, so there is nothing
for a worker to claim, hand off, or take over.

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
    """SIGTERM (the manager's shutdown) and SIGINT set `stop`; a second signal is ignored rather than killing us
    mid-cleanup."""
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


def _initialize_process():
    """What Sanic's `after_server_start` listeners do for a server worker, done here for this process: each
    process owns its FileConfig objects (they share `shared_ctx.*config`)."""
    from wrolpi.api_utils import api_app
    from wrolpi.contexts import initialize_configs_contexts

    initialize_configs_contexts(api_app)


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
    asyncio.run(serve_perpetual_loops(PERPETUAL_LOOPS))


def perpetual_process_needs_restart(workers: dict, now: float, last_request: float) -> bool:
    """True if the manager reports the perpetual process as gone and no restart was requested recently.

    `workers` is `app.m.workers` (a dict keyed by process name).  A missing entry is not "dead": the manager
    has not registered the process yet.
    """
    entry = workers.get(PERPETUAL_PROCESS_IDENT)
    if not entry or entry.get('state') not in PERPETUAL_PROCESS_DEAD_STATES:
        return False
    return (now - last_request) >= PERPETUAL_RESTART_COOLDOWN


_last_restart_request = 0.0


async def perpetual_process_health_check():
    """Runs in every server worker: ask the manager to restart the perpetual process if it has died.

    Sanic only marks a dead managed process FAILED; it does not restart it.  This is a restart request to the
    manager, not a takeover: the loops still run in exactly one process.
    """
    global _last_restart_request
    from wrolpi.api_utils import api_app

    multiplexer = getattr(api_app, 'multiplexer', None)
    if multiplexer is None:
        return
    try:
        workers = multiplexer.workers
    except Exception as e:
        logger.debug('Could not read worker states', exc_info=e)
        return
    now = time.time()
    if not perpetual_process_needs_restart(workers, now, _last_restart_request):
        return
    _last_restart_request = now
    state = workers[PERPETUAL_PROCESS_IDENT].get('state')
    logger.warning(f'Perpetual process is {state}; requesting restart pid={os.getpid()}')
    multiplexer.restart(PERPETUAL_PROCESS_IDENT)
