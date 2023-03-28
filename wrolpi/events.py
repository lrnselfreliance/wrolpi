import multiprocessing

__all__ = ['Events', 'get_events', 'send_event']

from datetime import datetime

from wrolpi.common import logger, iterify
from wrolpi.dates import now

logger = logger.getChild(__name__)

HISTORY_SIZE = 100
EVENTS_LOCK = multiprocessing.Lock()

EVENTS_HISTORY = multiprocessing.Manager().list()


class Events:

    @staticmethod
    def send_global_refresh_started(message: str = None):
        send_event('global_refresh_started', message, subject='refresh')

    @staticmethod
    def send_global_refresh_completed(message: str = None):
        send_event('global_refresh_completed', message, subject='refresh')

    @staticmethod
    def send_global_refresh_modeling_completed(message: str = None):
        send_event('global_refresh_modeling_completed', message, subject='refresh')

    @staticmethod
    def send_global_refresh_discovery_completed(message: str = None):
        send_event('global_refresh_discovery_completed', message, subject='refresh')

    @staticmethod
    def send_global_refresh_indexing_completed(message: str = None):
        send_event('global_refresh_indexing_completed', message, subject='refresh')

    @staticmethod
    def send_global_after_refresh_completed(message: str = None):
        send_event('global_after_refresh_completed', message, subject='refresh')

    @staticmethod
    def send_ready(message: str = None):
        send_event('ready', message)


def log_event(event: str, message: str = None, action: str = None, subject: str = None):
    log = f'{event=}'
    if subject:
        log = f'{log} {subject=}'
    if action:
        log = f'{log} {action=}'
    if message:
        log = f'{log} {message=}'
    logger.debug(log)


def send_event(event: str, message: str = None, action: str = None, subject: str = None):
    EVENTS_LOCK.acquire()
    try:
        # All events will be in time order, they should never be at the exact same time.
        dt = now()

        e = dict(
            action=action,
            dt=dt,
            event=event,
            message=message,
            subject=subject,
        )
        EVENTS_HISTORY.append(e)

        # Keep events below limit.
        while len(EVENTS_HISTORY) > HISTORY_SIZE:
            EVENTS_HISTORY.pop(0)
    finally:
        EVENTS_LOCK.release()

    log_event(event, message, action, subject)


@iterify(list)
def get_events(after: datetime = None):
    if not after:
        events = [i for i in EVENTS_HISTORY]
    else:
        events = [i for i in EVENTS_HISTORY if i['dt'] > after]

    # Most recent first.
    return events[::-1]
