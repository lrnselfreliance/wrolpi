"""Notifications for a secondary's syncs.

The Controller runs a sync (controller/lib/sync.py) and stops this API while it copies, so it cannot send the API's
events itself.  It records each sync's outcome in `config/sync_state.yaml`; the API reads that record and sends one
event per finished sync.  What it has announced is kept in its own file, which a sync never touches, so a restart
(and every sync restarts the API) neither repeats nor loses an announcement.
"""
from typing import Optional

import yaml

from wrolpi.common import logger, get_media_directory, is_secondary
from wrolpi.events import Events

logger = logger.getChild(__name__)

STATE_FILE = 'config/sync_state.yaml'
# Under config/.sync, which a sync never copies over or deletes.
ANNOUNCED_FILE = 'config/.sync/announced.yaml'
# A sync that was stopped on purpose is not news.
STOPPED = ('The sync was cancelled', 'WROL Mode was enabled')


def _read(path: str) -> dict:
    try:
        data = yaml.safe_load((get_media_directory() / path).read_text())
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def sync_message(state: dict) -> Optional[tuple]:
    """The event a finished sync deserves, as (kind, message), or None."""
    error = state.get('last_error')
    if state.get('state') == 'error':
        return 'failed', f'Sync from the primary failed: {error}'
    if error in STOPPED:
        return None
    copied, deleted = int(state.get('files_transferred') or 0), int(state.get('files_deleted') or 0)
    warnings = state.get('warnings') or []
    if not copied and not deleted and not warnings:
        # Within the window a sync runs every 15 minutes; one that changed nothing is not news.
        return None
    message = f'Synced {copied} files from the primary'
    if deleted:
        message += f'; {deleted} moved to the trash'
    if warnings:
        message += f'; {warnings[0]}'
    return 'completed', message


def notify_tick():
    """Send the event of a sync that finished since the last one announced."""
    if not is_secondary():
        return
    state = _read(STATE_FILE)
    finished_at = state.get('finished_at')
    if not finished_at or state.get('state') == 'running':
        return
    if _read(ANNOUNCED_FILE).get('finished_at') == finished_at:
        return
    if found := sync_message(state):
        kind, message = found
        if kind == 'failed':
            Events.send_sync_failed(message)
        else:
            Events.send_sync_completed(message)
    announced = get_media_directory() / ANNOUNCED_FILE
    try:
        announced.parent.mkdir(parents=True, exist_ok=True)
        announced.write_text(yaml.safe_dump(dict(finished_at=finished_at)))
    except OSError as e:
        logger.warning(f'Could not record the announced sync: {e}')
