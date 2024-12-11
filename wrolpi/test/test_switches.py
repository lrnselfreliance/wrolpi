import asyncio
import multiprocessing

import pytest

from wrolpi import switches
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
async def test_switches1(await_switches):
    global expected_context

    # Dispatch "test" switch, the switch handler should call the handler above, once.
    expected_context = {'foo': 'bar'}
    switches.activate_switch('test1', expected_context)
    await await_switches(timeout=2)
    assert count1.value == 1

    # Dispatching many times only causes switch handler to be called once because it is already pending.
    expected_context = {'foo': 'bar6'}
    # These contexts are overwritten.
    switch_handler_test1.activate_switch(context={'foo': 'bar1'})
    switch_handler_test1.activate_switch(context={'foo': 'bar2'})
    switch_handler_test1.activate_switch(context={'foo': 'bar3'})
    switch_handler_test1.activate_switch(context={'foo': 'bar4'})
    switch_handler_test1.activate_switch(context={'foo': 'bar5'})
    switch_handler_test1.activate_switch(context=expected_context)
    await await_switches(timeout=2)
    assert count1.value == 2


@register_switch_handler('test2')
async def switch_handler_test2(**context):
    count2.value += 1
    if count2.value == 2:
        raise Exception('second call error')


@pytest.mark.asyncio
async def test_perpetual_signal(await_switches):
    """Test that perpetual_signal survives errors."""
    # Signal event is dispatched again.
    switch_handler_test2.activate_switch()
    await asyncio.sleep(1)
    assert count2.value == 1

    # Error is logged.
    switch_handler_test2.activate_switch()
    await asyncio.sleep(1)
    assert count2.value == 2

    # Switch is dispatched again.
    switch_handler_test2.activate_switch()
    await asyncio.sleep(1)
    assert count2.value == 3


@pytest.mark.asyncio
async def test_invalid_activate_switch(await_switches):
    with pytest.raises(RuntimeError):
        switches.activate_switch('does not exist')

    with pytest.raises(RuntimeError):
        switches.activate_switch('test1', 'bad context')
