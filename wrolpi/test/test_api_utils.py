"""Tests for perpetual_signal cancellation / reschedule behavior."""
import asyncio
from unittest import mock

import pytest

from wrolpi.api_utils import (
    _app_is_stopping,
    _run_perpetual_iteration,
    api_app,
)


def test_app_is_stopping_false_by_default():
    api_app.ctx.perpetual_shutdown = False
    api_app.state.is_stopping = False
    # is_started/is_running are not a shutdown signal: docker Sanic workers
    # often have is_started=True and is_running=False while serving.
    api_app.state.is_started = True
    api_app.state.is_running = False
    assert _app_is_stopping() is False


def test_app_is_stopping_when_shutdown_flag_set():
    api_app.ctx.perpetual_shutdown = True
    try:
        assert _app_is_stopping() is True
    finally:
        api_app.ctx.perpetual_shutdown = False


def test_app_is_stopping_when_sanic_is_stopping():
    api_app.ctx.perpetual_shutdown = False
    api_app.state.is_stopping = True
    try:
        assert _app_is_stopping() is True
    finally:
        api_app.state.is_stopping = False


@pytest.mark.asyncio
async def test_perpetual_iteration_reschedules_after_unexpected_cancel(monkeypatch):
    """CancelledError must not silently kill the perpetual loop.

    Regression: perpetual_signal caught CancelledError, set cancelled=True,
    and skipped re-dispatch with no log.  The file-worker pump died for the
    life of the process.
    """
    dispatched = []

    async def boom():
        raise asyncio.CancelledError()

    async def fake_dispatch(event):
        dispatched.append(event)

    monkeypatch.setattr('wrolpi.api_utils.PYTEST', False)
    monkeypatch.setattr('wrolpi.api_utils._app_is_stopping', lambda: False)
    monkeypatch.setattr('wrolpi.api_utils._dispatch_perpetual', fake_dispatch)
    monkeypatch.setattr('wrolpi.api_utils.asyncio.sleep', mock.AsyncMock())

    await _run_perpetual_iteration(boom, 'wrolpi.perpetual.test_worker', sleep=0)
    assert dispatched == ['wrolpi.perpetual.test_worker']


@pytest.mark.asyncio
async def test_perpetual_iteration_stops_on_shutdown_cancel(monkeypatch):
    """CancelledError during shutdown must stay terminal (do not reschedule)."""
    dispatched = []

    async def boom():
        raise asyncio.CancelledError()

    async def fake_dispatch(event):
        dispatched.append(event)

    monkeypatch.setattr('wrolpi.api_utils.PYTEST', False)
    monkeypatch.setattr('wrolpi.api_utils._app_is_stopping', lambda: True)
    monkeypatch.setattr('wrolpi.api_utils._dispatch_perpetual', fake_dispatch)

    with pytest.raises(asyncio.CancelledError):
        await _run_perpetual_iteration(boom, 'wrolpi.perpetual.test_worker', sleep=0)
    assert dispatched == []


def test_claim_perpetual_tasks_when_never_started(async_client):
    """The first worker to start must claim the perpetual loops."""
    from wrolpi.api_utils import _claim_perpetual_tasks, api_app

    api_app.shared_ctx.perpetual_tasks_started.clear()
    assert _claim_perpetual_tasks(api_app) is True


def test_claim_perpetual_tasks_skips_when_owner_is_alive(async_client):
    """A live owner keeps the single-process loops from starting twice."""
    import os
    from wrolpi.api_utils import _claim_perpetual_tasks, api_app

    api_app.shared_ctx.perpetual_tasks_started.set()
    api_app.shared_ctx.perpetual_tasks_owner_pid.value = os.getpid()
    assert _claim_perpetual_tasks(api_app) is False


def test_claim_perpetual_tasks_when_owner_process_is_dead(async_client):
    """A dead owner must not block a replacement worker from restarting the loops.

    ``perpetual_tasks_started`` is a shared Event.  Sanic docker runs with
    auto_reload, and a worker crash/recycle leaves that Event set.  The
    replacement process's after_server_start then no-ops, and file processing
    (plus downloads, switches, …) is dead until a full API restart.

    This is the unconfirmed wedge from the 2026-08-18 incident: last file-worker
    activity from one PID, then silence across every process, recovered only by
    restarting the API.
    """
    from wrolpi.api_utils import _claim_perpetual_tasks, api_app

    api_app.shared_ctx.perpetual_tasks_started.set()
    # A PID that cannot be running on this host.
    api_app.shared_ctx.perpetual_tasks_owner_pid.value = 2**31 - 1
    assert _claim_perpetual_tasks(api_app) is True
    assert api_app.shared_ctx.perpetual_tasks_owner_pid.value != 2**31 - 1, \
        'claimer must record this process as the new owner'


def test_perpetual_events_include_file_worker_when_not_claimed(async_client):
    """Every Sanic worker must run the file-worker pump, even if it does not
    own the other perpetual tasks.

    Otherwise a live owner whose *task* died (CancelledError before the
    reschedule fix) still wedges file operations in every other process.
    """
    import os
    from wrolpi.api_utils import (
        FILE_WORKER_PERPETUAL_EVENT,
        _perpetual_events_for_this_process,
        api_app,
    )

    api_app.shared_ctx.perpetual_tasks_started.set()
    api_app.shared_ctx.perpetual_tasks_owner_pid.value = os.getpid()
    events = _perpetual_events_for_this_process(api_app)
    assert events == [FILE_WORKER_PERPETUAL_EVENT]


@pytest.mark.asyncio
async def test_perpetual_iteration_reschedules_after_error(monkeypatch):
    """Ordinary exceptions are logged and the loop continues."""
    dispatched = []

    async def boom():
        raise RuntimeError('worker exploded')

    async def fake_dispatch(event):
        dispatched.append(event)

    monkeypatch.setattr('wrolpi.api_utils.PYTEST', False)
    monkeypatch.setattr('wrolpi.api_utils._app_is_stopping', lambda: False)
    monkeypatch.setattr('wrolpi.api_utils._dispatch_perpetual', fake_dispatch)
    monkeypatch.setattr('wrolpi.api_utils.asyncio.sleep', mock.AsyncMock())

    await _run_perpetual_iteration(boom, 'wrolpi.perpetual.test_worker', sleep=0)
    assert dispatched == ['wrolpi.perpetual.test_worker']
