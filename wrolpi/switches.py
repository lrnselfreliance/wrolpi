import asyncio
import inspect
import multiprocessing
from functools import partial
from typing import Dict, Mapping

from wrolpi.api_utils import api_app, logger, perpetual_signal
from wrolpi.vars import PYTEST

SWITCH_HANDLERS: Dict[str, callable] = dict()


def activate_switch(switch_name: str, context: dict = None):
    """
    Activate a named switch.  Replaces the context of the previous call if it has not yet been handled.
    """
    if switch_name not in SWITCH_HANDLERS:
        raise RuntimeError(f'Cannot activate switch {switch_name}, it has not been registered.')

    switches: Dict[str, dict] = api_app.shared_ctx.switches
    switches_changed: multiprocessing.Event = api_app.shared_ctx.switches_changed
    context = context or dict()
    if not isinstance(context, Mapping):
        raise RuntimeError('Switch context must be a dict (for kwargs)')

    switches_changed.set()
    switches.update({**switches, switch_name: context})


def register_switch_handler(switch_name: str):
    """Register a handler for a switch.  The switch can be activated by name using `active_switch`, or by the
    `activate_switch` method attached to the wrapped function.

    >>> def func():
    >>>     pass

    >>> @register_switch_handler('unique_name')
    >>> async def func_handler(**context):
    >>>     # handle the switch
    >>>
    >>> func_handler.activate_switch()
    """

    def wrapper(handler: callable):
        # Add `handler` function to global dict, this will be called by `switch_worker`.
        SWITCH_HANDLERS[switch_name] = handler

        handler.activate_switch = partial(activate_switch, switch_name)
        return handler

    return wrapper


@perpetual_signal(sleep=0.1)
async def switch_worker():
    """Watches `api_app.shared_ctx.switches` for new activated switches, handles each one at a time."""
    switches: dict = api_app.shared_ctx.switches

    # Wait for the switches to be changed.
    switches_changed: multiprocessing.Event = api_app.shared_ctx.switches_changed
    switches_changed.wait(timeout=1 if PYTEST else None)

    switch_name = None
    try:
        # Get new switch and its context.  Handle each switch one at a time.
        switch_name = next(iter(switches))
        context = switches.pop(switch_name)
        # Call handler with the stored context, await coroutine, if any.
        handler = SWITCH_HANDLERS[switch_name]
        coro = handler(**context)
        if inspect.iscoroutine(coro):
            await coro
    except StopIteration:
        # No switches to handle.
        pass
    except KeyError:
        logger.critical(f'No switch handler defined for: {switch_name}')
    finally:
        switches_changed.clear()


async def await_switches(timeout: int = 10):
    if not PYTEST:
        raise RuntimeError('This function is only for testing purposes')

    async def _():
        while True:
            if len(api_app.shared_ctx.switches):
                await asyncio.sleep(0.1)
                continue
            if api_app.shared_ctx.switches_changed.is_set():
                await asyncio.sleep(0.1)
                continue
            # All switches handled.
            return

    try:
        await asyncio.wait_for(_(), timeout=timeout)
    except asyncio.TimeoutError:
        raise RuntimeError('Timed out waiting for switches')
