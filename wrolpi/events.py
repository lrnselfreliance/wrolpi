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
    def send_global_refresh_indexing_completed(message: str = None):
        send_event('global_refresh_indexing_completed', message, subject='refresh')

    @staticmethod
    def send_global_refresh_delete_completed(message: str = None):
        send_event('global_refresh_delete_completed', message, subject='refresh')

    @staticmethod
    def send_ready(message: str = None):
        send_event('ready', message)

    @staticmethod
    def send_directory_refresh_started(message: str):
        send_event('global_directory_refresh_started', message, subject='refresh_directory')

    @staticmethod
    def send_directory_refresh_completed(message: str):
        send_event('global_directory_refresh_completed', message, subject='refresh_directory')

    @staticmethod
    def send_refresh_required(message: str = None):
        send_event('refresh_required', message, subject='refresh_required')

    @staticmethod
    def send_singlefile_missing():
        send_event('singlefile_missing', subject='install')


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

    logger.debug(f'Sent event {event}')


@iterify(list)
def get_events(after: datetime = None):
    if not after:
        events = [i for i in EVENTS_HISTORY]
    else:
        events = [i for i in EVENTS_HISTORY if i['dt'] > after]

    # Most recent first.
    return events[::-1]
