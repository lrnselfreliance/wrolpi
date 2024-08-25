import asyncio
import multiprocessing

import pytest

from wrolpi.switches import register_switch_handler

count1 = multiprocessing.Value('i', 0)
count2 = multiprocessing.Value('i', 0)
expected_context = None


@register_switch_handler('test1')  # wrolpi.switch.test signal
async def switch_handler_test1(**context):
    assert context == expected_context
    count1.value += 1
    # Sleep so that multiple dispatches are ignored.
    await asyncio.sleep(0.5)


@pytest.mark.asyncio
async def test_switches(test_async_client):
    global expected_context

    # Call API so server actually starts.
    await test_async_client.get('/api/echo')

    # Dispatch "test" switch, the switch handler should call the handler above, once.
    expected_context = {'foo': 'bar'}
    await test_async_client.sanic_app.dispatch('wrolpi.switch.test1', context=expected_context)
    await asyncio.sleep(1)
    assert count1.value == 1

    # Dispatching many times only causes switch handler to be called once because it is already pending.
    expected_context = {'foo': 'bar6'}
    # These contexts are overwritten.
    await switch_handler_test1.dispatch(context={'foo': 'bar1'})
    await switch_handler_test1.dispatch(context={'foo': 'bar2'})
    await switch_handler_test1.dispatch(context={'foo': 'bar3'})
    await switch_handler_test1.dispatch(context={'foo': 'bar4'})
    await switch_handler_test1.dispatch(context={'foo': 'bar5'})
    await switch_handler_test1.dispatch(context=expected_context)
    await asyncio.sleep(1)
    assert count1.value == 2


@register_switch_handler('test2')
async def switch_handler_test2(**context):
    count2.value += 1
    if count2.value == 2:
        raise Exception('second call error')


@pytest.mark.asyncio
async def test_perpetual_signal(test_async_client):
    """Test that perpetual_signal survives errors."""
    # Signal event is dispatched again.
    await switch_handler_test2.dispatch()
    await asyncio.sleep(1)
    assert count2.value == 1

    # Error is logged.
    await switch_handler_test2.dispatch()
    await asyncio.sleep(1)
    assert count2.value == 2

    # Switch is dispatched again.
    await switch_handler_test2.dispatch()
    await asyncio.sleep(1)
    assert count2.value == 3
