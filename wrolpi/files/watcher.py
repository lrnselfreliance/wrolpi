import logging

from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileMovedEvent
from watchdog.observers import Observer

from wrolpi import flags
from wrolpi.common import logger, get_media_directory
from wrolpi.files import lib as files_lib

logger = logger.getChild(__name__)

watchdog_logger = logging.getLogger('watchdog.observers.inotify_buffer')
watchdog_logger.setLevel(logging.WARNING)


class MediaDirectoryWatcher(FileSystemEventHandler):

    def on_modified(self, event: FileModifiedEvent):
        if event.is_directory:
            return

        logger.debug(f'MediaDirectoryWatcher.on_modified {event=}')
        files_lib.add_to_refresh_queue(event.src_path)

    def on_created(self, event: FileCreatedEvent):
        if event.is_directory:
            return

        logger.debug(f'MediaDirectoryWatcher.on_created {event=}')
        files_lib.add_to_refresh_queue(event.src_path)

    def on_moved(self, event: FileMovedEvent):
        if event.is_directory:
            return

        logger.debug(f'MediaDirectoryWatcher.on_moved {event=}')
        files_lib.add_to_refresh_queue(event.src_path)
        files_lib.add_to_refresh_queue(event.dest_path)

    def on_deleted(self, event):
        if event.is_directory:
            return

        logger.debug(f'MediaDirectoryWatcher.on_deleted {event=}')
        files_lib.add_to_refresh_queue(event.src_path)


# Only one observer will be started.
observer = Observer()


def start_file_watcher():
    if flags.media_directory_watcher.is_set():
        return

    flags.media_directory_watcher.set()
    logger.debug('Starting MediaDirectoryWatcher')
    media_directory = str(get_media_directory())
    observer.schedule(MediaDirectoryWatcher(), media_directory, recursive=True)
    observer.start()
