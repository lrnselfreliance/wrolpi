"""sync.yaml: how this WROLPi syncs.

These settings belong to this machine: they are never copied from a primary (a secondary's sync.yaml says it is a
secondary; its primary's says otherwise), so they are kept apart from wrolpi.yaml, whose library settings are.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from wrolpi.common import ConfigFile
from wrolpi.sync.status import get_backup_status, update_backup_status


@dataclass
class SyncConfigValidator:
    version: int = None
    # 'primary' or 'secondary'; a secondary copies its library from `primary_url` (see controller/lib/sync.py).
    role: str = None
    primary_url: str = None
    # The daily window ('HH:MM') in which a secondary syncs; none means only "Sync Now".
    window_start: str = None
    window_end: str = None
    # Folders (relative to the media directory) a secondary never downloads from its primary.
    sync_excluded_directories: list[str] = field(default_factory=list)
    # Days a secondary keeps a file its primary deleted or replaced (in `.sync-trash`); None never deletes.
    delete_after_days: int = None
    # A second drive this WROLPi copies its media directory to (see wrolpi.sync.backup), and the UUID of the drive
    # that must be mounted there.
    backup_directory: str = None
    backup_device_uuid: str = None
    # The daily window ('HH:MM') in which the backup drive is written; none means only "Back Up Now".
    backup_window_start: str = None
    backup_window_end: str = None
    # Folders (relative to the media directory) never copied to the backup drive.
    backup_excluded_directories: list[str] = field(default_factory=list)
    # Days the backup drive keeps a file deleted (or replaced) in the media directory, in `.backup-trash`; None never
    # deletes.
    backup_delete_after_days: int = None
    # When a backup last finished without errors (ISO 8601); kept so it is known after a restart.
    backup_last_success_at: str = None


# Long enough to notice a file that should not have been deleted on the primary.
DEFAULT_DELETE_AFTER_DAYS = 30


class SyncConfig(ConfigFile):
    file_name = 'sync.yaml'
    default_config = dict(
        version=0,
        role='primary',
        primary_url=None,
        window_start=None,
        window_end=None,
        sync_excluded_directories=[],
        delete_after_days=DEFAULT_DELETE_AFTER_DAYS,
        backup_directory=None,
        backup_device_uuid=None,
        backup_window_start=None,
        backup_window_end=None,
        backup_excluded_directories=[],
        backup_delete_after_days=DEFAULT_DELETE_AFTER_DAYS,
        backup_last_success_at=None,
    )
    validator = SyncConfigValidator

    def import_config(self, file=None, send_events=False):
        super().import_config(file, send_events)
        # The backup's status lives in memory; a restart would otherwise forget when the last backup succeeded.
        if self.backup_last_success_at and not get_backup_status()['last_success_at']:
            update_backup_status(last_success_at=self.backup_last_success_at)

    @property
    def role(self) -> str:
        return self._config.get('role') or 'primary'

    @property
    def primary_url(self) -> Optional[str]:
        return self._config.get('primary_url')

    @property
    def window_start(self) -> Optional[str]:
        return self._config.get('window_start')

    @property
    def window_end(self) -> Optional[str]:
        return self._config.get('window_end')

    @property
    def sync_excluded_directories(self) -> List[str]:
        return list(self._config.get('sync_excluded_directories') or [])

    @property
    def delete_after_days(self) -> Optional[int]:
        """None never deletes.  A sync.yaml written before this setting has no key, and gets the default."""
        if 'delete_after_days' not in self._config:
            return DEFAULT_DELETE_AFTER_DAYS
        return self._config['delete_after_days']

    @property
    def backup_directory(self) -> Optional[str]:
        return self._config.get('backup_directory')

    @property
    def backup_device_uuid(self) -> Optional[str]:
        return self._config.get('backup_device_uuid')

    @property
    def backup_window_start(self) -> Optional[str]:
        return self._config.get('backup_window_start')

    @property
    def backup_window_end(self) -> Optional[str]:
        return self._config.get('backup_window_end')

    @property
    def backup_excluded_directories(self) -> List[str]:
        return list(self._config.get('backup_excluded_directories') or [])

    @property
    def backup_delete_after_days(self) -> Optional[int]:
        """None never deletes.  A sync.yaml written before this setting has no key, and gets the default."""
        if 'backup_delete_after_days' not in self._config:
            return DEFAULT_DELETE_AFTER_DAYS
        return self._config['backup_delete_after_days']

    @property
    def backup_last_success_at(self) -> Optional[str]:
        return self._config.get('backup_last_success_at')


SYNC_CONFIG: SyncConfig = SyncConfig()


def get_sync_config() -> SyncConfig:
    return SYNC_CONFIG
