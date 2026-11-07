"""Tests for the perpetual / per-worker loop registrars and the per-worker task listeners."""
import asyncio
from unittest import mock

import pytest

from wrolpi import perpetual
from wrolpi.api_utils import api_app, perpetual_signal, per_worker_task, start_per_worker_tasks, \
    stop_per_worker_tasks
from wrolpi.perpetual import PerpetualLoop


def test_per_worker_listeners_are_registered_on_the_app():
    """A typo in the listener event name would leave per-worker tasks never started or never stopped."""
    registered = {(i.event, i.listener) for i in api_app._future_listeners}
    assert ('after_server_start', start_per_worker_tasks) in registered
    assert ('before_server_stop', stop_per_worker_tasks) in registered


def test_registrars_are_noops_under_pytest():
    async def f():
        pass

    assert perpetual_signal(sleep=3)(f) is f
    assert per_worker_task(sleep=3)(f) is f
    assert all(i.func is not f for i in perpetual.PERPETUAL_LOOPS)
    assert all(i.func is not f for i in perpetual.PER_WORKER_TASKS)


def test_registrars_record_one_loop_each(monkeypatch):
    """Outside pytest, each decorator registers exactly one loop in its own registry and returns the function."""
    singletons, everywhere_ = [], []
    monkeypatch.setattr('wrolpi.api_utils.PYTEST', False)
    monkeypatch.setattr('wrolpi.api_utils.PERPETUAL_LOOPS', singletons)
    monkeypatch.setattr('wrolpi.api_utils.PER_WORKER_TASKS', everywhere_)

    async def singleton():
        pass

    async def everywhere():
        pass

    assert perpetual_signal(sleep=7)(singleton) is singleton
    assert per_worker_task(sleep=2)(everywhere) is everywhere

    assert [(i.name, i.sleep) for i in singletons] == [('singleton', 7)]
    assert [(i.name, i.sleep) for i in everywhere_] == [('everywhere', 2)]


@pytest.mark.asyncio
async def test_per_worker_tasks_start_and_stop_with_the_server(monkeypatch):
    """after_server_start runs every per-worker loop as a task; before_server_stop ends them."""
    calls = []

    async def tick():
        calls.append(1)

    monkeypatch.setattr('wrolpi.api_utils.PER_WORKER_TASKS', [PerpetualLoop('tick', tick, 0.01)])
    app = mock.Mock()
    app.ctx = mock.Mock()

    await start_per_worker_tasks(app)
    await asyncio.sleep(0.05)
    assert calls, 'the per-worker loop should be running'
    assert len(app.ctx.per_worker_tasks) == 1

    await stop_per_worker_tasks(app)
    assert all(t.done() for t in app.ctx.per_worker_tasks)
    count = len(calls)
    await asyncio.sleep(0.03)
    assert len(calls) == count, 'the loop must not run after stop'


@pytest.mark.asyncio
async def test_stop_per_worker_tasks_without_start():
    """Stopping an app that never started per-worker tasks (tests, or a startup failure) is harmless."""
    app = mock.Mock()
    app.ctx = mock.Mock(spec=[])  # no per_worker_* attributes
    await stop_per_worker_tasks(app)


@pytest.mark.asyncio
async def test_finalizing_signals_again_adds_no_routes(test_session, async_client):
    """Each start of the app finalizes the signal router again (the test client, Sanic's startup, and
    `finalize_signals_after_auto_routes`).  Sanic's finalize appends a `sanic.__signal__.__init__` handler before it
    checks whether the router is finalized, so every start left routes behind; after a few hundred tests in one
    process the compiled router was too deep to compile (RecursionError)."""
    await async_client.get('/api/echo')
    before = len(api_app.signal_router.routes)

    # An app that is already started.
    api_app.signalize()
    api_app.signalize()
    assert len(api_app.signal_router.routes) == before

    # What each start does (see `unfinalize_signals_for_auto_routes`).
    api_app.signal_router.reset()
    api_app.signalize()
    assert len(api_app.signal_router.routes) == before
    assert api_app.signal_router.finalized

    # Signals still dispatch.
    request, response = await async_client.get('/api/echo')
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_server_start_finalizes_signals_once(test_session, async_client):
    """sanic-ext's automatic HEAD and OPTIONS routes must not re-finalize the signal router once per route; each
    finalize also left one more `sanic.__signal__` route behind."""
    def finalizes():
        return len([i for i in api_app.signal_router.routes if str(i.path).startswith('sanic.__signal__.')])

    # Other tests started the shared app before.
    before = finalizes()
    await async_client.get('/api/echo')
    assert finalizes() - before < 10, f'{finalizes() - before} signal router finalizes'

    # The automatic routes still work.
    request, response = await async_client.options('/api/status')
    assert response.status_code == 204
    assert set(response.headers['allow'].split(',')) == {'GET', 'HEAD', 'OPTIONS'}
    request, response = await async_client.head('/api/status')
    assert response.status_code == 200
