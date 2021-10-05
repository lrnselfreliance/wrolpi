BEFORE_STARTUP_FUNCTIONS = []


def before_startup(func: callable):
    """
    Run a callable before startup of the WROLPi API.
    """
    BEFORE_STARTUP_FUNCTIONS.append(func)
    return func
