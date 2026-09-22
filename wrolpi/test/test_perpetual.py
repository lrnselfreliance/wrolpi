"""Tests for the perpetual process runner and the per-worker health check (wrolpi/perpetual.py)."""
import asyncio
import os
import signal
import threading
import time
from unittest import mock

import pytest

from wrolpi.perpetual import (
    PERPETUAL_PROCESS_IDENT,
    PERPETUAL_RESTART_COOLDOWN,
    PerpetualLoop,
    perpetual_process_needs_restart,
    run_loop,
    run_loops,
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
    """Only a process the manager reports as gone triggers a restart request, at most once per cooldown."""
    now = 1_000_000.0
    dead = {PERPETUAL_PROCESS_IDENT: {'pid': 123, 'state': 'FAILED'}}
    alive = {PERPETUAL_PROCESS_IDENT: {'pid': 123, 'state': 'STARTED'}}

    assert perpetual_process_needs_restart(dead, now, last_request=0) is True
    assert perpetual_process_needs_restart(dead, now, last_request=now - 1) is False, 'within cooldown'
    assert perpetual_process_needs_restart(dead, now, last_request=now - PERPETUAL_RESTART_COOLDOWN) is True
    for state in ('STARTING', 'STARTED', 'RESTARTING', 'NONE'):
        alive[PERPETUAL_PROCESS_IDENT]['state'] = state
        assert perpetual_process_needs_restart(alive, now, last_request=0) is False, state
    assert perpetual_process_needs_restart({}, now, last_request=0) is False, 'not registered yet is not dead'
    assert perpetual_process_needs_restart({'Sanic-Server-0': {'state': 'FAILED'}}, now, 0) is False


@pytest.mark.asyncio
async def test_health_check_requests_restart_once(async_client, monkeypatch):
    """Every server worker runs this; a dead perpetual process gets one restart request per cooldown."""
    from wrolpi import perpetual
    from wrolpi.api_utils import api_app

    multiplexer = mock.Mock()
    multiplexer.workers = {PERPETUAL_PROCESS_IDENT: {'pid': 1, 'state': 'FAILED'}}
    monkeypatch.setattr(api_app, 'multiplexer', multiplexer, raising=False)
    monkeypatch.setattr(perpetual, '_last_restart_request', 0.0)

    await perpetual.perpetual_process_health_check()
    await perpetual.perpetual_process_health_check()
    multiplexer.restart.assert_called_once_with(PERPETUAL_PROCESS_IDENT)

    multiplexer.workers = {PERPETUAL_PROCESS_IDENT: {'pid': 2, 'state': 'STARTED'}}
    monkeypatch.setattr(perpetual, '_last_restart_request', 0.0)
    await perpetual.perpetual_process_health_check()
    multiplexer.restart.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_without_multiplexer_is_a_noop(async_client, monkeypatch):
    from wrolpi import perpetual
    from wrolpi.api_utils import api_app

    monkeypatch.delattr(api_app, 'multiplexer', raising=False)
    await perpetual.perpetual_process_health_check()
