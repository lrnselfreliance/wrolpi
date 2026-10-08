"""Tests for file progress (how far the user is through a file) and recently_viewed.yaml."""
import json
from datetime import timedelta
from http import HTTPStatus

import pytest
import yaml

from wrolpi import dates
from wrolpi.errors import ValidationError
from wrolpi.files.models import FileGroup
from wrolpi.files.progress import normalize_progress, get_recently_viewed_config, RECENTLY_VIEWED_LIMIT
from wrolpi.files.worker import file_worker, FileTask, FileTaskType


def read_recently_viewed(test_directory) -> list:
    with (test_directory / 'config/recently_viewed.yaml').open() as fh:
        return yaml.safe_load(fh)['files']


@pytest.mark.parametrize('progress,position,expected', [
    # A video part way through keeps its position.
    (0.5, dict(kind='time', seconds=300.0), (0.5, dict(kind='time', seconds=300.0))),
    # Finished files have no position.
    (0.95, dict(kind='time', seconds=570), (1.0, None)),
    (1.5, dict(kind='page', page=40), (1.0, None)),
    # Barely started files are not worth resuming.
    (0.2, dict(kind='time', seconds=9.9), (0.0, None)),
    (0.005, dict(kind='epub', cfi='epubcfi(/6/2!/4/2)'), (0.0, None)),
    (0.1, dict(kind='page', page=0), (0.0, None)),
    (-1, None, (0.0, None)),
    # Pages and CFIs.
    (0.3, dict(kind='page', page=12), (0.3, dict(kind='page', page=12))),
    (0.3, dict(kind='epub', cfi='epubcfi(/6/14!/4/2)', updated_at=1760000000000),
     (0.3, dict(kind='epub', cfi='epubcfi(/6/14!/4/2)', updated_at=1760000000000))),
    # Unknown keys are dropped.
    (0.3, dict(kind='page', page=3, evil='x'), (0.3, dict(kind='page', page=3))),
])
def test_normalize_progress(progress, position, expected):
    assert normalize_progress(progress, position) == expected


@pytest.mark.parametrize('progress,position', [
    ('half', None),
    (True, None),
    (float('nan'), None),
    (0.5, dict(kind='time', seconds='300')),
    (0.5, dict(kind='time', seconds=-1)),
    (0.5, dict(kind='page', page=1.5)),
    (0.5, dict(kind='page', page=True)),
    (0.5, dict(kind='epub', cfi='javascript:alert(1)')),
    (0.5, dict(kind='epub', cfi='epubcfi(' + 'a' * 1_000 + ')')),
    (0.5, dict(kind='scroll', fraction=0.5)),
    (0.5, 'time'),
])
def test_normalize_progress_invalid(progress, position):
    with pytest.raises(ValidationError):
        normalize_progress(progress, position)


@pytest.mark.asyncio
async def test_progress_api(test_session, async_client, test_directory, make_files_structure):
    """Progress is stored on the FileGroup, returned with the file, and is a view."""
    make_files_structure(['videos/movie.mp4'])

    body = dict(file='videos/movie.mp4', progress=0.4, position=dict(kind='time', seconds=480.5))
    request, response = await async_client.post('/api/files/progress', content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK
    assert response.json == dict(progress=0.4, position=dict(kind='time', seconds=480.5))

    fg, = test_session.query(FileGroup).all()
    assert fg.viewed
    assert fg.progress == 0.4
    assert fg.position == dict(kind='time', seconds=480.5)

    # The next request sees what was stored.
    request, response = await async_client.post('/api/files/file', content=json.dumps(
        dict(file='videos/movie.mp4', skip_tracking=True)))
    assert response.json['file']['progress'] == 0.4
    assert response.json['file']['position'] == dict(kind='time', seconds=480.5)

    # Rewinding is allowed; the last write wins.
    body = dict(file='videos/movie.mp4', progress=0.2, position=dict(kind='time', seconds=240))
    request, response = await async_client.post('/api/files/progress', content=json.dumps(body))
    test_session.expire_all()
    assert fg.progress == 0.2
    assert fg.position == dict(kind='time', seconds=240)

    # Start over.
    request, response = await async_client.post('/api/files/progress/clear',
                                                content=json.dumps(dict(file='videos/movie.mp4')))
    assert response.status_code == HTTPStatus.NO_CONTENT
    test_session.expire_all()
    assert fg.progress is None
    assert fg.position is None
    assert fg.viewed, 'A file that starts over has still been viewed'


@pytest.mark.asyncio
async def test_progress_api_errors(test_session, async_client, test_directory, make_files_structure):
    make_files_structure(['videos/movie.mp4'])

    body = dict(file='videos/movie.mp4', progress=0.4, position=dict(kind='scroll', fraction=0.4))
    request, response = await async_client.post('/api/files/progress', content=json.dumps(body))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    body = dict(file='videos/missing.mp4', progress=0.4, position=dict(kind='time', seconds=40))
    request, response = await async_client.post('/api/files/progress', content=json.dumps(body))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # A file outside the media directory.
    outside = test_directory.parent / 'outside.mp4'
    outside.touch()
    try:
        for file in ('../outside.mp4', str(outside)):
            body = dict(file=file, progress=0.4, position=dict(kind='time', seconds=40))
            request, response = await async_client.post('/api/files/progress', content=json.dumps(body))
            assert response.status_code == HTTPStatus.BAD_REQUEST
            request, response = await async_client.post('/api/files/progress/clear',
                                                        content=json.dumps(dict(file=file)))
            assert response.status_code == HTTPStatus.BAD_REQUEST
    finally:
        outside.unlink()

    assert test_session.query(FileGroup).count() == 0


@pytest.mark.asyncio
async def test_progress_ignored_directory(test_session, async_client, test_directory, make_files_structure,
                                          test_wrolpi_config, await_switches):
    """Files in ignored directories are not tracked."""
    from wrolpi.common import get_wrolpi_config
    make_files_structure(['private/movie.mp4'])
    get_wrolpi_config().ignored_directories = [str(test_directory / 'private')]
    await await_switches()

    body = dict(file='private/movie.mp4', progress=0.4, position=dict(kind='time', seconds=480))
    request, response = await async_client.post('/api/files/progress', content=json.dumps(body))
    assert response.status_code == HTTPStatus.OK
    assert test_session.query(FileGroup).count() == 0


@pytest.mark.asyncio
async def test_progress_saves_config_when_final(test_session, async_client, test_directory, make_files_structure):
    """Only a final progress (pause, close) saves the config; a heartbeat during playback writes only the DB."""
    make_files_structure(['videos/movie.mp4'])
    config_file = test_directory / 'config/recently_viewed.yaml'

    body = dict(file='videos/movie.mp4', progress=0.4, position=dict(kind='time', seconds=480))
    await async_client.post('/api/files/progress', content=json.dumps(body))
    assert not config_file.exists()

    body['final'] = True
    await async_client.post('/api/files/progress', content=json.dumps(body))
    entry, = read_recently_viewed(test_directory)
    assert entry['path'] == 'videos/movie.mp4'
    assert entry['progress'] == 0.4
    assert entry['position'] == dict(kind='time', seconds=480.0)
    assert dates.strptime_ms(entry['viewed'])

    # Starting over saves the config.
    await async_client.post('/api/files/progress/clear', content=json.dumps(dict(file='videos/movie.mp4')))
    entry, = read_recently_viewed(test_directory)
    assert 'progress' not in entry and 'position' not in entry


@pytest.mark.asyncio
async def test_view_saves_config(test_session, async_client, test_directory, make_files_structure, refresh_files,
                                 await_background_tasks, await_switches):
    """Opening a file saves it in the recently viewed config."""
    make_files_structure({'docs/notes.txt': 'notes'})
    await refresh_files()
    await await_switches()
    # The refresh saved the config, with nothing viewed yet.
    assert read_recently_viewed(test_directory) == []

    await async_client.post('/api/files/file', content=json.dumps(dict(file='docs/notes.txt')))
    # Viewing a file is a background task, which activates the switch.
    await await_background_tasks()
    await await_switches()

    entry, = read_recently_viewed(test_directory)
    assert entry['path'] == 'docs/notes.txt'
    assert 'progress' not in entry


@pytest.mark.asyncio
async def test_recently_viewed_dump_order_and_limit(test_session, async_client, test_directory, make_files_structure,
                                                    monkeypatch):
    """The config holds the most recently viewed files, newest first."""
    monkeypatch.setattr('wrolpi.files.progress.RECENTLY_VIEWED_LIMIT', 2)
    old, middle, new, never = make_files_structure(['old.txt', 'middle.txt', 'new.txt', 'never.txt'])
    now = dates.now()
    for path, viewed in ((old, now - timedelta(days=2)), (middle, now - timedelta(days=1)), (new, now), (never, None)):
        fg = FileGroup.from_paths(test_session, path)
        fg.viewed = viewed
    test_session.commit()

    config = get_recently_viewed_config()
    config.dump_config()
    config.save()

    assert [i['path'] for i in read_recently_viewed(test_directory)] == ['new.txt', 'middle.txt']
    assert RECENTLY_VIEWED_LIMIT == 1_000


@pytest.mark.asyncio
async def test_recently_viewed_import(test_session, async_client, test_directory, make_files_structure,
                                      video_file_factory):
    """A wiped database gets its viewing history back from the config.  The newer `viewed` wins."""
    _, book, newer = make_files_structure(['videos/movie.en.vtt', 'books/book.epub', 'videos/newer.mp4'])
    video_file_factory(test_directory / 'videos/movie.mp4')
    now = dates.now()

    # This file was viewed after the config was written (e.g. while WROLPi was starting).
    newer_fg = FileGroup.from_paths(test_session, newer)
    newer_fg.viewed = now
    newer_fg.progress = 0.8
    newer_fg.position = dict(kind='time', seconds=800.0)
    test_session.commit()

    config_file = test_directory / 'config/recently_viewed.yaml'
    config_file.parent.mkdir(exist_ok=True)
    config_file.write_text(yaml.dump(dict(version=3, files=[
        dict(path='videos/newer.mp4', viewed=(now - timedelta(hours=1)).isoformat(), progress=0.1,
             position=dict(kind='time', seconds=100)),
        dict(path='videos/movie.mp4', viewed=(now - timedelta(hours=2)).isoformat(), progress=0.5,
             position=dict(kind='time', seconds=600)),
        dict(path='books/book.epub', viewed=(now - timedelta(hours=3)).isoformat(), progress=1.0),
        # The file was deleted.
        dict(path='videos/deleted.mp4', viewed=(now - timedelta(hours=4)).isoformat(), progress=0.5),
        # Invalid entries are ignored.
        dict(path='videos/movie.mp4', viewed='not a date'),
        dict(path='books/book.epub', viewed=now.isoformat(), progress=0.5, position=dict(kind='scroll')),
        'not an entry',
    ])))

    config = get_recently_viewed_config()
    config.import_config()
    assert config.successful_import

    test_session.expire_all()
    fgs = {i.primary_path.name: i for i in test_session.query(FileGroup)}
    assert set(fgs) == {'movie.mp4', 'book.epub', 'newer.mp4'}
    # The FileGroup created by the import has all its files.
    assert len(fgs['movie.mp4'].files) == 2

    assert fgs['movie.mp4'].progress == 0.5
    assert fgs['movie.mp4'].position == dict(kind='time', seconds=600.0)
    assert fgs['movie.mp4'].viewed == now - timedelta(hours=2)
    assert fgs['book.epub'].progress == 1.0
    assert fgs['book.epub'].position is None
    # The DB was newer.
    assert fgs['newer.mp4'].progress == 0.8
    assert fgs['newer.mp4'].position == dict(kind='time', seconds=800.0)

    # The config round trips.
    config.dump_config()
    config.save()
    assert [i['path'] for i in read_recently_viewed(test_directory)] == \
           ['videos/newer.mp4', 'videos/movie.mp4', 'books/book.epub']


@pytest.mark.asyncio
async def test_recently_viewed_not_dumped_before_import(test_session, async_client, test_directory,
                                                        make_files_structure):
    """A dump before the import would replace the history the import has yet to apply."""
    movie, = make_files_structure(['videos/movie.mp4'])
    config_file = test_directory / 'config/recently_viewed.yaml'
    config_file.parent.mkdir(exist_ok=True)
    config_file.write_text(yaml.dump(dict(version=1, files=[
        dict(path='videos/movie.mp4', viewed=dates.now().isoformat(), progress=0.5,
             position=dict(kind='time', seconds=600))])))

    config = get_recently_viewed_config()
    config.successful_import = False
    config.dump_config()
    assert read_recently_viewed(test_directory)[0]['progress'] == 0.5
    assert config.files == []


@pytest.mark.asyncio
async def test_recently_viewed_follows_move(test_session, async_client, test_directory, make_files_structure):
    """Progress follows a moved file, and the config is saved with the new path."""
    movie, = make_files_structure(['videos/movie.mp4'])
    body = dict(file='videos/movie.mp4', progress=0.4, position=dict(kind='time', seconds=480), final=True)
    await async_client.post('/api/files/progress', content=json.dumps(body))
    assert read_recently_viewed(test_directory)[0]['path'] == 'videos/movie.mp4'

    destination = test_directory / 'watched'
    destination.mkdir()
    file_worker.private_queue.put_nowait(FileTask(FileTaskType.move, [movie], destination=destination))
    await file_worker.process_queue()
    # The next request awaits the switches the move activated.
    await async_client.post('/api/files/file', content=json.dumps(dict(file='watched/movie.mp4', skip_tracking=True)))

    test_session.expire_all()
    fg, = test_session.query(FileGroup).all()
    assert fg.primary_path == destination / 'movie.mp4'
    assert fg.position == dict(kind='time', seconds=480.0)
    entry, = read_recently_viewed(test_directory)
    assert entry['path'] == 'watched/movie.mp4'
    assert entry['progress'] == 0.4
