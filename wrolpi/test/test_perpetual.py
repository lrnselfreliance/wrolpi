"""Tests for the perpetual process runner and the per-worker health check (wrolpi/perpetual.py)."""
import asyncio
import multiprocessing
import os
import pathlib
import select
import signal
import sys
import threading
import time
from unittest import mock

import pytest
from sanic.worker.constants import ProcessState
from sanic.worker.process import Worker

from wrolpi import perpetual
from wrolpi.perpetual import (
    PERPETUAL_PROCESS_DEAD_STATES,
    PERPETUAL_PROCESS_IDENT,
    PERPETUAL_PROCESS_NAME,
    PERPETUAL_RESTART_COOLDOWN,
    PerpetualLoop,
    perpetual_process_needs_restart,
    reconcile_after_predecessor,
    register_perpetual_process,
    run_loop,
    run_loops,
    run_perpetual_process,
    serve_perpetual_loops,
)


@pytest.mark.asyncio
async def test_run_loop_calls_sleeps_and_survives_errors():
    """The loop keeps calling its function after an exception, and stops promptly when told to."""
    calls = []
    stop = asyncio.Event()

    async def flaky():
        calls.append(time.time())
        if len(calls) == 2:
            raise RuntimeError('second call fails')
        if len(calls) == 4:
            stop.set()

    await asyncio.wait_for(run_loop(PerpetualLoop('flaky', flaky, sleep=0.01), stop), timeout=2)

    assert len(calls) == 4, 'the loop must continue after an error and stop when asked'


@pytest.mark.asyncio
async def test_run_loop_does_not_reenter_a_long_call():
    """A slow iteration is awaited; the next call starts only after it returns."""
    active = 0
    overlaps = []
    stop = asyncio.Event()
    calls = 0

    async def slow():
        nonlocal active, calls
        calls += 1
        active += 1
        overlaps.append(active)
        await asyncio.sleep(0.02)
        active -= 1
        if calls == 3:
            stop.set()

    await asyncio.wait_for(run_loop(PerpetualLoop('slow', slow, sleep=0), stop), timeout=2)
    assert max(overlaps) == 1


@pytest.mark.asyncio
async def test_run_loops_cancels_everything_on_stop():
    """Setting `stop` cancels every loop task; a loop that ignores cancellation is abandoned, not waited for forever."""
    stop = asyncio.Event()
    cancelled = []

    async def sleeper():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append('sleeper')
            raise

    async def stubborn():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append('stubborn')
            await asyncio.sleep(3600)  # refuses to die

    loops = [PerpetualLoop('sleeper', sleeper, 1), PerpetualLoop('stubborn', stubborn, 1)]
    runner = asyncio.ensure_future(run_loops(loops, stop, cancel_timeout=0.1))
    await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(runner, timeout=2)

    assert sorted(cancelled) == ['sleeper', 'stubborn']


@pytest.mark.asyncio
async def test_serve_perpetual_loops_stops_on_sigterm():
    """The perpetual process exits when the manager sends SIGTERM."""
    ticks = []

    async def tick():
        ticks.append(1)

    initialized = []
    with mock.patch('wrolpi.perpetual._shutdown_singletons', mock.AsyncMock()) as shutdown:
        serving = asyncio.ensure_future(
            serve_perpetual_loops([PerpetualLoop('tick', tick, 0.01)], initialize=lambda: initialized.append(1)))
        await asyncio.sleep(0.05)
        assert ticks, 'loop should be running before the signal'
        # From another thread, as the manager (another process) would.
        threading.Timer(0.01, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
        await asyncio.wait_for(serving, timeout=2)

    shutdown.assert_awaited_once()
    assert initialized == [1], 'per-process initialization must run once before the loops'


def test_perpetual_process_needs_restart():
    """Only a process the manager reports as gone triggers a restart request, at most once per cooldown.

    The dead/alive partition is checked against Sanic's own ProcessState enum, so a rename fails here."""
    now = 1_000_000.0
    names = {state.name for state in ProcessState}
    assert PERPETUAL_PROCESS_DEAD_STATES <= names, 'a dead state is not a Sanic ProcessState'
    for state in ProcessState:
        workers = {PERPETUAL_PROCESS_IDENT: {'pid': 123, 'state': state.name}}
        expected = state.name in PERPETUAL_PROCESS_DEAD_STATES
        assert perpetual_process_needs_restart(workers, now, last_request=0) is expected, state.name

    dead = {PERPETUAL_PROCESS_IDENT: {'pid': 123, 'state': ProcessState.FAILED.name}}
    assert perpetual_process_needs_restart(dead, now, last_request=now - 1) is False, 'within cooldown'
    assert perpetual_process_needs_restart(dead, now, last_request=now - PERPETUAL_RESTART_COOLDOWN) is True
    assert perpetual_process_needs_restart({}, now, last_request=0) is False, 'not registered yet is not dead'
    assert perpetual_process_needs_restart({'Sanic-Server-0-0': {'state': 'FAILED'}}, now, 0) is False


def test_process_ident_matches_sanic_naming():
    """`PERPETUAL_PROCESS_IDENT` is what Sanic's Worker actually names the managed process."""
    worker = Worker(PERPETUAL_PROCESS_NAME, PERPETUAL_PROCESS_NAME, lambda: None, {}, multiprocessing.get_context(),
                    {}, 1)
    assert [p.name for p in worker.processes] == [PERPETUAL_PROCESS_IDENT]


def test_register_perpetual_process_is_transient():
    """`transient=True` is load-bearing: it restarts the process on auto-reload and makes it restartable."""
    app = mock.Mock()
    register_perpetual_process(app)
    app.manager.manage.assert_called_once_with(PERPETUAL_PROCESS_NAME, run_perpetual_process, {}, transient=True)


@pytest.mark.asyncio
async def test_health_check_requests_restart_once(async_client, monkeypatch):
    """Every server worker runs this; a dead perpetual process gets one restart request per cooldown."""
    from wrolpi import perpetual
    from wrolpi.api_utils import api_app

    multiplexer = mock.Mock()
    multiplexer.workers = {PERPETUAL_PROCESS_IDENT: {'pid': 1, 'state': 'FAILED'}}
    monkeypatch.setattr(api_app, 'multiplexer', multiplexer, raising=False)
    api_app.shared_ctx.perpetual_restart_requested_at.value = 0.0

    await perpetual.perpetual_process_health_check()
    # A second worker (different process, so a different module-level state) sees the same FAILED tick.
    monkeypatch.setattr(perpetual, '_last_restart_request', 0.0)
    await perpetual.perpetual_process_health_check()
    multiplexer.restart.assert_called_once_with(PERPETUAL_PROCESS_IDENT)
    assert api_app.shared_ctx.perpetual_restart_requested_at.value > 0, 'the claim is recorded in shared_ctx'

    multiplexer.workers = {PERPETUAL_PROCESS_IDENT: {'pid': 2, 'state': 'STARTED'}}
    api_app.shared_ctx.perpetual_restart_requested_at.value = 0.0
    await perpetual.perpetual_process_health_check()
    multiplexer.restart.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_without_multiplexer_is_a_noop(async_client, monkeypatch):
    from wrolpi import perpetual
    from wrolpi.api_utils import api_app

    monkeypatch.delattr(api_app, 'multiplexer', raising=False)
    await perpetual.perpetual_process_health_check()


def _wait_for_byte(fd: int, timeout: float) -> bytes:
    ready, _, _ = select.select([fd], [], [], timeout)
    return os.read(fd, 1) if ready else b''


@pytest.mark.parametrize('sig', [signal.SIGINT, signal.SIGTERM], ids=['SIGINT (manager shutdown)', 'SIGTERM (restart)'])
def test_run_perpetual_process_exits_cleanly_on_signal(async_client, monkeypatch, sig):
    """The real entry point, in a real forked process, with a real background task alive, exits 0 on the signals
    the manager sends.  (This is a sync test so the fork does not inherit a running event loop.)"""
    ready_r, ready_w = os.pipe()

    async def loop_with_live_background_task():
        from wrolpi.common import background_task
        background_task(asyncio.sleep(3600))
        # The byte doubles as the assertion that the entry point marked this process as the perpetual one.
        os.write(ready_w, b'x' if perpetual.IN_PERPETUAL_PROCESS else b'n')

    monkeypatch.setattr(perpetual, 'PERPETUAL_LOOPS', [PerpetualLoop('bg', loop_with_live_background_task, 3600)])
    assert perpetual.IN_PERPETUAL_PROCESS is False, 'the test process is not the perpetual process'
    # The forked test process must not touch the test database; the reconcile step has its own tests below.
    monkeypatch.setattr(perpetual, 'reconcile_after_predecessor', lambda app: {})

    process = multiprocessing.get_context('fork').Process(target=run_perpetual_process)
    process.start()
    try:
        assert _wait_for_byte(ready_r, 10) == b'x', 'the perpetual process did not start its loop as the perpetual process'
        os.kill(process.pid, sig)
        process.join(15)
        assert process.exitcode == 0, f'perpetual process exited {process.exitcode}'
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        os.close(ready_r)
        os.close(ready_w)


def test_run_perpetual_process_refuses_to_run_no_loops(monkeypatch):
    """Under `spawn` nothing would be registered; that must fail loudly instead of running zero loops."""
    monkeypatch.setattr(perpetual, 'PERPETUAL_LOOPS', [])
    with pytest.raises(RuntimeError, match='fork'):
        run_perpetual_process()


def _crash_once_then_sleep(marker: str):
    if not pathlib.Path(marker).exists():
        pathlib.Path(marker).touch()
        sys.exit(1)
    while True:
        time.sleep(1)


def test_sanic_manager_marks_failed_and_restart_revives(test_directory):
    """Against Sanic's real WorkerManager: a crashed managed process becomes FAILED (which the health check
    keys on) and `restart(process_names=[ident])` starts a replacement with a new pid."""
    from multiprocessing import Pipe, Manager
    from sanic.worker.manager import WorkerManager

    saved = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    ctx = multiprocessing.get_context('fork')
    state_manager = Manager()
    worker_state = state_manager.dict()
    manager = None
    try:
        manager = WorkerManager(1, _crash_once_then_sleep, {'marker': str(test_directory / 'server-never')},
                                ctx, Pipe(), worker_state)
        # The fake "server" must not crash: give it an existing marker.
        (test_directory / 'server-never').touch()
        manager.manage(PERPETUAL_PROCESS_NAME, _crash_once_then_sleep, {'marker': str(test_directory / 'marker')},
                       transient=True)
        manager.start()

        deadline = time.time() + 15
        while time.time() < deadline:
            manager._sync_states()
            if worker_state.get(PERPETUAL_PROCESS_IDENT, {}).get('state') == ProcessState.FAILED.name:
                break
            time.sleep(0.1)
        else:
            pytest.fail(f'never FAILED: {dict(worker_state)}')
        dead_pid = worker_state[PERPETUAL_PROCESS_IDENT]['pid']

        manager.restart(process_names=[PERPETUAL_PROCESS_IDENT])

        deadline = time.time() + 15
        while time.time() < deadline:
            manager._sync_states()
            entry = worker_state.get(PERPETUAL_PROCESS_IDENT, {})
            if entry.get('pid') not in (None, dead_pid) and entry.get('state') not in PERPETUAL_PROCESS_DEAD_STATES:
                break
            time.sleep(0.1)
        else:
            pytest.fail(f'not revived: {dict(worker_state)}')
        assert pathlib.Path(test_directory / 'marker').exists()
    finally:
        if manager is not None:
            for process in list(manager.processes):
                try:
                    process._current_process.kill()
                except Exception:
                    pass
        state_manager.shutdown()
        for sig, handler in saved.items():
            signal.signal(sig, handler)


@pytest.mark.asyncio
async def test_reconcile_after_predecessor(async_client, test_session, monkeypatch, flags_lock):
    """A restarted perpetual process cleans up what a predecessor that died mid-work left behind."""
    from wrolpi.api_utils import api_app
    from wrolpi.downloader import Download, download_manager
    from wrolpi.files.worker import file_worker
    from wrolpi import jobs, flags

    # A domain still claimed, a Download still pending, a Job still running under a dead pid, a file job running,
    # and the jobs lock still held by the dead process.
    download_manager.processing_domains = ['example.com']
    test_session.add(Download(url='https://example.com/a', downloader='video', status='pending'))
    test_session.add(Download(url='https://example.com/b', downloader='video', status='new'))
    test_session.commit()
    api_app.shared_ctx.jobs['dead'] = dict(id='dead', name='x', status=jobs.RUNNING, pid=2 ** 31 - 1, kwargs={},
                                           created_at='', started_at='', finished_at=None, error=None)
    api_app.shared_ctx.jobs['mine'] = dict(id='mine', name='x', status=jobs.RUNNING, pid=os.getpid(), kwargs={},
                                           created_at='', started_at='', finished_at=None, error=None)
    file_worker._set_job_status('fj', 'running')
    file_worker.update_status(status='refreshing')
    flags.file_worker_counting.set()          # perpetual-only: cleared whoever held it
    flags.global_refresh_active.set()         # perpetual-only, set() not entered: cleared
    flags.file_worker_modeling.set()          # shared, holder dead: cleared
    api_app.shared_ctx.flag_holders['file_worker_modeling'] = 2 ** 31 - 1
    flags.map_search_building.set()           # shared, holder is a live API worker: kept
    api_app.shared_ctx.flag_holders['map_search_building'] = os.getppid()
    flags.file_worker_indexing.set()          # shared, no holder recorded: kept (cannot tell)
    flags.file_worker_busy.set()              # not a reconciled flag (a live move may hold it): kept
    flags.db_up.set()  # not an in-progress flag; must survive
    assert api_app.shared_ctx.jobs_lock.acquire(timeout=1)
    monkeypatch.setattr(perpetual, 'SHARED_LOCK_HEAL_TIMEOUT', 0.1)

    report = reconcile_after_predecessor(api_app)

    assert report['locks'] == ['jobs_lock']
    assert api_app.shared_ctx.jobs_lock.acquire(timeout=1), 'the orphaned lock is usable again'
    api_app.shared_ctx.jobs_lock.release()
    assert report['jobs'] == 1
    assert api_app.shared_ctx.jobs['dead']['status'] == jobs.FAILED
    assert api_app.shared_ctx.jobs['mine']['status'] == jobs.RUNNING, 'this process\'s own Job is untouched'
    assert report['processing_domains'] == 1 and list(download_manager.processing_domains) == []
    assert report['downloads'] == 1
    test_session.expire_all()
    assert {d.url: d.status for d in test_session.query(Download)} == \
           {'https://example.com/a': 'new', 'https://example.com/b': 'new'}
    assert report['file_worker_jobs'] == 1 and file_worker._jobs['fj']['status'] == 'failed'
    assert file_worker.status['status'] == 'idle' and report['file_worker_status'] is True
    assert report['flags'] == ['file_worker_counting', 'global_refresh_active', 'file_worker_modeling']
    assert not flags.file_worker_counting.is_set() and not flags.global_refresh_active.is_set()
    assert not flags.file_worker_modeling.is_set() and 'file_worker_modeling' not in api_app.shared_ctx.flag_holders
    assert flags.map_search_building.is_set(), 'a flag held by a live process is not touched'
    assert flags.file_worker_indexing.is_set(), 'a shared flag with no recorded holder is not touched'
    assert flags.file_worker_busy.is_set(), 'file_worker_busy is not reconciled'
    assert flags.db_up.is_set(), 'only in-progress flags are cleared'
    with flags.file_worker_counting:  # usable again; this raised "flag is already set" before
        pass
    for name in ('map_search_building', 'file_worker_indexing', 'file_worker_busy'):
        getattr(flags, name).clear()
    api_app.shared_ctx.flag_holders.clear()

    # Idempotent: a clean state reports nothing.
    assert not any(reconcile_after_predecessor(api_app).values())


def test_flag_context_manager_records_its_holder(async_client, flags_lock):
    """`with flag:` records this pid so a later reconcile can tell an orphaned flag from a live holder."""
    from wrolpi import flags
    from wrolpi.api_utils import api_app

    assert flags.file_worker_modeling.holder_pid() is None
    with flags.file_worker_modeling:
        assert flags.file_worker_modeling.holder_pid() == os.getpid()
        assert api_app.shared_ctx.flag_holders['file_worker_modeling'] == os.getpid()
    assert flags.file_worker_modeling.holder_pid() is None
    assert not flags.file_worker_modeling.is_set()
