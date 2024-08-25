import inspect
from typing import Dict

from wrolpi.api_utils import api_app, logger, perpetual_signal


@api_app.signal('wrolpi.switch.<switch_name>')
async def switcher(switch_name: str, **context):
    """Add new switch and context to the global switch queue."""
    switches: Dict[str, dict] = api_app.shared_ctx.switches
    switches.update({**switches, switch_name: context})


SWITCH_HANDLERS: Dict[str, callable] = dict()


def register_switch_handler(switch_name: str):
    """Register a handler for a switch.  The switch can be triggered using a Sanic signal, or, using the `.dispatch`
    method that will be attached to the provided handler.

    >>> def func():
    >>>     pass

    >>> @register_switch_handler('unique_name')
    >>> async def func_handler(**context):
    >>>     # handle the switch
    >>>
    >>> await func_handler.dispatch()
    """
    if '.' in switch_name:
        raise ValueError('switch name cannot contain .')

    def wrapper(handler: callable):
        if not inspect.iscoroutinefunction(handler):
            raise ValueError('handler must be a coroutine')

        # Add `handler` function to global dict, this will be called by `switch_worker`.
        SWITCH_HANDLERS[switch_name] = handler

        async def dispatch(context: dict = None):
            await api_app.dispatch(f'wrolpi.switch.{switch_name}', context=context)

        handler.dispatch = dispatch
        return handler

    return wrapper


@perpetual_signal(sleep=0.1)
async def switch_worker():
    """Watches `api_app.shared_ctx.switches` for new activated switches, handles each one at a time."""
    switches: dict = api_app.shared_ctx.switches
    switch_name = None
    try:
        # Get new switch and its context.  Handle each switch one at a time.
        switch_name = next(iter(switches))
        context = switches.pop(switch_name)
        handler = SWITCH_HANDLERS[switch_name]
        await handler(**context)
    except StopIteration:
        # No switches to handle.
        pass
    except KeyError:
        logger.critical(f'No switch handler defined for: {switch_name}')
