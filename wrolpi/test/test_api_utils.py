"""Tests for the perpetual / per-worker loop registrars and the per-worker task listeners."""
import asyncio
from unittest import mock

import pytest

from wrolpi import perpetual
from wrolpi.api_utils import perpetual_signal, per_worker_task, start_per_worker_tasks, stop_per_worker_tasks
from wrolpi.perpetual import PerpetualLoop


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
