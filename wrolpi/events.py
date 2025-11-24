__all__ = ['Events', 'get_events']

from datetime import datetime

from wrolpi.common import logger, iterify
from wrolpi.dates import now

logger = logger.getChild(__name__)

HISTORY_SIZE = 100


class Events:

    @staticmethod
    def send_global_refresh_started(message: str = None):
        send_event('global_refresh_started', message, subject='refresh')

    @staticmethod
    def send_refresh_completed(message: str = None):
        send_event('refresh_completed', message, subject='refresh')

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

    @staticmethod
    def send_downloads_disabled(message: str = None):
        send_event('downloads_disabled', message, subject='downloads')

    @staticmethod
    def send_user_notify(message: str, url: str = None):
        send_event('user_notify_message', message, subject='user_notify', url=url)

    @staticmethod
    def send_directory_refresh(message: str = None):
        send_event('directory_refresh', message, subject='refresh')

    @staticmethod
    def send_deleted(message: str = None):
        send_event('deleted', message, subject='deleted')

    @staticmethod
    def send_created(message: str = None):
        send_event('created', message, subject='created')

    @staticmethod
    def send_map_import_complete(message: str = None):
        send_event('map_import_complete', message, subject='map')

    @staticmethod
    def send_map_import_failed(message: str = None):
        send_event('map_import_failed', message, subject='map')

    @staticmethod
    def send_shutdown(message: str = None):
        send_event('shutdown', message, subject='shutdown')

    @staticmethod
    def send_shutdown_failed(message: str = None):
        send_event('shutdown_failed', message, subject='shutdown')

    @staticmethod
    def send_file_move_completed(message: str = None):
        send_event('file_move_completed', message, subject='refresh')

    @staticmethod
    def send_file_move_failed(message: str = None):
        send_event('file_move_failed', message, subject='refresh')

    @staticmethod
    def send_config_import_failed(message: str = None):
        send_event('config_import_failed', message, subject='configs')

    @staticmethod
    def send_config_save_failed(message: str = None):
        send_event('config_save_failed', message, subject='configs')

    @classmethod
    def send_archive_uploaded(cls, message: str = None, url: str = None):
        send_event('upload_archive', message, subject='upload', url=url)

    @classmethod
    def send_upload_archive_failed(cls, message: str = None):
        send_event('upload_archive_failed', message, subject='upload')


def log_event(event: str, message: str = None, action: str = None, subject: str = None):
    log = f'{event=}'
    if subject:
        log = f'{log} {subject=}'
    if action:
        log = f'{log} {action=}'
    if message:
        log = f'{log} {message=}'
    logger.debug(log)


def send_event(event: str, message: str = None, action: str = None, subject: str = None, url: str = None):
    from wrolpi.api_utils import api_app
    api_app.shared_ctx.events_lock.acquire()
    try:
        # All events will be in time order, they should never be at the exact same time.
        dt = now()

        e = dict(
            action=action,
            dt=dt,
            event=event,
            message=message,
            subject=subject,
            url=url,
        )
        api_app.shared_ctx.events_history.append(e)

        # Keep events below limit.
        while len(api_app.shared_ctx.events_history) > HISTORY_SIZE:
            api_app.shared_ctx.events_history.pop(0)
    finally:
        api_app.shared_ctx.events_lock.release()

    log_event(event, message, action, subject)


@iterify(list)
def get_events(after: datetime = None):
    from wrolpi.api_utils import api_app
    events_history = api_app.shared_ctx.events_history
    if not after:
        events = [i for i in events_history]
    else:
        events = [i for i in events_history if i['dt'] > after]

    # Most recent first.
    return events[::-1]
