import asyncio
import inspect
import logging
import multiprocessing
from functools import partial
from typing import Dict, Mapping, Protocol

from wrolpi.api_utils import api_app, logger, perpetual_signal
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)

SWITCH_HANDLERS: Dict[str, callable] = dict()


def activate_switch(switch_name: str, context: dict = None):
    """
    Activate a named switch.  Replaces the context of the previous call if it has not yet been handled.
    """
    if switch_name not in SWITCH_HANDLERS:
        raise RuntimeError(f'Cannot activate switch {switch_name}, it has not been registered.')

    switches_lock: multiprocessing.Lock = api_app.shared_ctx.switches_lock
    if switches_lock.acquire(timeout=5):
        try:
            try:
                switches = api_app.shared_ctx.switches
            except AttributeError:
                raise RuntimeError(
                    f'Sanic shared_ctx has not been initialized.  If testing, use `async_client` fixture.')

            switches_changed: multiprocessing.Event = api_app.shared_ctx.switches_changed
            context = context or dict()
            if not isinstance(context, Mapping):
                raise RuntimeError('Switch context must be a dict (for kwargs)')

            switches_changed.set()
            switches.update({**switches.copy(), switch_name: context})
            if logger.isEnabledFor(logging.DEBUG):
                # Switches can be difficult to troubleshoot.  Log the function that activates a switch.
                caller_frame_record = inspect.stack()[1]
                frame = caller_frame_record[0]
                info = inspect.getframeinfo(frame)
                logger.debug(f'activate_switch: {switch_name} called by {info.function} in {info.filename}')
        finally:
            switches_lock.release()
    else:
        raise RuntimeError(f'Failed to acquire switches_lock lock to set switch {switch_name}')


class ActivateSwitchMethod(Protocol):
    """Adds type hinting for @register_switch_handler use."""

    def activate_switch(self, context: dict = None) -> None:
        ...


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
        if switch_name in SWITCH_HANDLERS and not PYTEST:
            raise RuntimeError(f'register_switch_handler: switch name already taken {switch_name}')

        # Add `handler` function to global dict, this will be called by `switch_worker`.
        SWITCH_HANDLERS[switch_name] = handler

        setattr(handler, 'activate_switch', partial(activate_switch, switch_name))
        return handler

    return wrapper


DEBUG_LOGGED = False


@perpetual_signal(sleep=0.1, run_while_testing=True)
async def switch_worker():
    """Watches `api_app.shared_ctx.switches` for new activated switches, handles each one at a time."""
    global DEBUG_LOGGED
    if not DEBUG_LOGGED:
        logger.debug('switch_worker started')
        DEBUG_LOGGED = True

    # Wait for the switches to be changed.
    switches_changed: multiprocessing.Event = api_app.shared_ctx.switches_changed

    switch_name = None
    try:
        # Get new switch and its context.  Handle each switch one at a time.
        switches_changed.wait(timeout=1)
        switches: dict = api_app.shared_ctx.switches
        with api_app.shared_ctx.switches_lock:
            switch_name, context = switches.popitem()
            switches_keys = list(switches.keys())
        # Call handler with the stored context, await coroutine, if any.
        handler = SWITCH_HANDLERS[switch_name]
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'switch_worker handling {switch_name} of {switches_keys}')
        else:
            logger.info(f'switch_worker handling {switch_name} of {len(switches_keys)}')
        coro = handler(**context)
        if inspect.iscoroutine(coro):
            # Handler is async.
            await coro
        logger.debug(f'switch_worker completed {switch_name}')
    except TimeoutError:
        # `switches_changed` is not set.
        pass
    except StopIteration:
        # No switches to handle.
        pass
    except KeyError:
        # `switches` is empty, or `switch_name` not in `SWITCH_HANDLER`
        if switch_name:
            logger.critical(f'No switch handler defined for: {switch_name}')
    finally:
        # Clear only after task is complete to avoid
        switches_changed.clear()


async def await_switches(timeout: int = 10):
    if not PYTEST:
        raise RuntimeError('This function is only for testing purposes')

    count = 0
    while count < (timeout * 10):
        count += 1
        if api_app.shared_ctx.switches:
            await asyncio.sleep(0.1)
            continue
        if api_app.shared_ctx.switches_changed.is_set():
            await asyncio.sleep(0.1)
            continue
        # All switches handled.
        break
    else:
        raise RuntimeError('Timed out waiting for switches.  Did you remember to use the `await_switches` fixture?')
