"""sync.yaml: how this WROLPi syncs.

These settings belong to this machine: they are never copied from a primary (a secondary's sync.yaml says it is a
secondary; its primary's says otherwise), so they are kept apart from wrolpi.yaml, whose library settings are.
"""
from dataclasses import dataclass
from typing import Optional

from wrolpi.common import ConfigFile
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod
from wrolpi.sync.status import get_backup_status, update_backup_status


@dataclass
class SyncConfigValidator:
    version: int = None
    # 'primary' or 'secondary'; a secondary copies its library from `primary_url` (see wrolpi.sync.lib).
    role: str = None
    primary_url: str = None
    # The daily window ('HH:MM') in which a secondary syncs; none means only "Sync Now".
    window_start: str = None
    window_end: str = None
    # A second drive this WROLPi copies its media directory to (see wrolpi.sync.backup), and the UUID of the drive
    # that must be mounted there.
    backup_directory: str = None
    backup_device_uuid: str = None
    # The daily window ('HH:MM') in which the backup drive is written; none means only "Back Up Now".
    backup_window_start: str = None
    backup_window_end: str = None
    # When a backup last finished without errors (ISO 8601); kept so it is known after a restart.
    backup_last_success_at: str = None


class SyncConfig(ConfigFile):
    file_name = 'sync.yaml'
    default_config = dict(
        version=0,
        role='primary',
        primary_url=None,
        window_start=None,
        window_end=None,
        backup_directory=None,
        backup_device_uuid=None,
        backup_window_start=None,
        backup_window_end=None,
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
    def backup_last_success_at(self) -> Optional[str]:
        return self._config.get('backup_last_success_at')


SYNC_CONFIG: SyncConfig = SyncConfig()


def get_sync_config() -> SyncConfig:
    return SYNC_CONFIG


@register_switch_handler('save_sync_config')
def save_sync_config():
    get_sync_config().save()


save_sync_config: ActivateSwitchMethod
