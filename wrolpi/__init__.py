import wrolpi.files.api  # noqa  Import from files so the blueprint is attached.
import wrolpi.scrape_downloader  # noqa

BEFORE_STARTUP_FUNCTIONS = []


def before_startup(func: callable):
    """
    Run a callable before startup of the WROLPi API.  This will be called (and blocked on) once.
    """
    if func not in BEFORE_STARTUP_FUNCTIONS:
        BEFORE_STARTUP_FUNCTIONS.append(func)
    return func


def after_startup(func: callable):
    """
    Run a function after the startup of the WROLPi Sanic API.  This will be run for each process!
    """
    from wrolpi.api_utils import api_app
    api_app.after_server_start(func)
    return func
