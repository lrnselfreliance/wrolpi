import pytest
import yaml

from wrolpi.sync import notify


@pytest.fixture
def state(test_directory):
    """Write the Controller's record of the last sync."""

    def write(**fields):
        record = dict(state='idle', finished_at='2026-11-19T03:00:00+00:00', last_error=None, files_transferred=0,
                      files_deleted=0, warnings=[])
        record.update(fields)
        (test_directory / notify.STATE_FILE).write_text(yaml.safe_dump(record))

    return write


@pytest.mark.parametrize('fields, expected', [
    (dict(files_transferred=12, files_deleted=3),
     ('completed', 'Synced 12 files from the primary; 3 moved to the trash')),
    (dict(files_transferred=1), ('completed', 'Synced 1 files from the primary')),
    (dict(warnings=['Some files changed on the primary']),
     ('completed', 'Synced 0 files from the primary; Some files changed on the primary')),
    (dict(state='error', last_error='The primary did not answer'),
     ('failed', 'Sync from the primary failed: The primary did not answer')),
    # Nothing changed: within the window that is every 15 minutes.
    (dict(), None),
    (dict(last_error='The sync was cancelled', files_transferred=4), None),
    (dict(last_error='WROL Mode was enabled'), None),
])
def test_sync_message(fields, expected):
    record = dict(state='idle', last_error=None, files_transferred=0, files_deleted=0, warnings=[])
    record.update(fields)
    assert notify.sync_message(record) == expected


def test_each_sync_is_announced_once(async_client, test_directory, test_wrolpi_config, make_secondary, state,
                                     events_fixture):
    """The API is restarted by every sync, so what it announced is kept in a file of its own."""
    make_secondary('https://primary.example')
    state(files_transferred=5)
    notify.notify_tick()
    events_fixture.assert_has_event('sync_completed')
    assert yaml.safe_load((test_directory / notify.ANNOUNCED_FILE).read_text()) == dict(
        finished_at='2026-11-19T03:00:00+00:00')

    # Again, and after a restart: the same sync is not announced twice.
    notify.notify_tick()
    assert len(events_fixture.get_by_name('sync_completed')) == 1

    state(state='error', last_error='The primary did not answer', finished_at='2026-11-19T03:20:00+00:00')
    notify.notify_tick()
    events_fixture.assert_has_event('sync_failed', 'Sync from the primary failed: The primary did not answer')

    # A sync that changed nothing is recorded as seen, and not announced.
    state(finished_at='2026-11-19T03:40:00+00:00')
    notify.notify_tick()
    assert len(events_fixture.get_by_name('sync_completed')) == 1
    assert yaml.safe_load((test_directory / notify.ANNOUNCED_FILE).read_text())['finished_at'] == \
        '2026-11-19T03:40:00+00:00'


def test_not_while_running_and_not_on_a_primary(async_client, test_directory, test_wrolpi_config, make_secondary,
                                                state):
    state(state='running', finished_at=None)
    notify.notify_tick()
    assert not (test_directory / notify.ANNOUNCED_FILE).exists(), 'on a primary nothing is read'
    make_secondary('https://primary.example')
    notify.notify_tick()
    assert not (test_directory / notify.ANNOUNCED_FILE).exists(), 'a running sync has nothing to announce'
