import inspect
import multiprocessing

BEFORE_STARTUP_FUNCTIONS = []


def before_startup(func: callable):
    """
    Run a callable before startup of the WROLPi API.  This will be called (and blocked on) once.
    """
    BEFORE_STARTUP_FUNCTIONS.append(func)
    return func


def after_startup(func: callable):
    """
    Run a function after the startup of the WROLPi Sanic API.  This will be run for each process!
    """
    from .root_api import api_app
    api_app.after_server_start(func)
    return func


def limit_concurrent(limit: int):
    """
    Wrapper that limits the amount of concurrently running functions.
    """
    sema = multiprocessing.Semaphore(value=limit)

    def wrapper(func: callable):
        if inspect.iscoroutinefunction(func):
            async def wrapped(*a, **kw):
                acquired = sema.acquire(block=False)
                if not acquired:
                    return
                return await func(*a, **kw)

            return wrapped
        else:
            def wrapped(*a, **kw):
                acquired = sema.acquire(block=False)
                if not acquired:
                    return
                return func(*a, **kw)

            return wrapped

    return wrapper
