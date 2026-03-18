import json

import pytest

from wrolpi.common import get_wrolpi_config
from wrolpi.errors import UnknownFile
from wrolpi.files.models import FileGroup


def test_file_group_find_by_id(test_session, make_files_structure):
    """FileGroup.find_by_id should accept session as first argument, id as second."""
    make_files_structure({'test.txt': 'test contents'})

    # Create a FileGroup from the file
    from wrolpi.common import get_media_directory
    fg = FileGroup.from_paths(test_session, get_media_directory() / 'test.txt')
    test_session.add(fg)
    test_session.flush()

    # Session must be first argument (session-first pattern)
    found = FileGroup.find_by_id(test_session, fg.id)
    assert found is not None
    assert found.id == fg.id

    # Non-existent ID should raise UnknownFile
    with pytest.raises(UnknownFile):
        FileGroup.find_by_id(test_session, 99999)


@pytest.mark.asyncio
async def test_file_group_move(async_client, test_session, test_directory, video_factory, test_wrolpi_config):
    """Any new or renamed files are adopted during FileGroup.move."""
    # Disable ffprobe json file creation to avoid unexpected files in test assertions
    get_wrolpi_config().save_ffprobe_json = False

    video = video_factory(title='video', with_poster_ext='.webp')
    test_session.commit()

    # Move one of the FileGroup's files.  It should be moved as well.
    video.poster_path.rename(video.poster_path.with_suffix('.jpg'))

    # Move the FilGroup.
    new_primary_path = video.video_path.with_name('new name')
    video.file_group.move(new_primary_path)

    # New file is discovered and adopted, missing file is removed.
    assert video.file_group.my_paths() == [
        (test_directory / 'videos/NO CHANNEL/new name.jpg'),
        (test_directory / 'videos/NO CHANNEL/new name.mp4'),
    ]


@pytest.mark.asyncio
async def test_add_tag_overload(async_client, test_session, make_files_structure, tag_factory, refresh_files):
    """FileGroup.add_tag and FileGroup.untag use `singeldispatch`."""
    make_files_structure({'foo.txt': 'foo contents'})
    await refresh_files()
    foo: FileGroup = test_session.query(FileGroup).one()

    one, two = await tag_factory(), await tag_factory()

    foo.add_tag(test_session, one.name)
    assert set(foo.tag_names) == {'one'}, 'Tag should have been found by name'
    foo.add_tag(test_session, two.id)
    assert set(foo.tag_names) == {'one', 'two'}, 'Tag should have been found by ID.'

    foo.untag(test_session, one.name)
    assert set(foo.tag_names) == {'two'}, 'Tag should have been found by name'
    foo.untag(test_session, two.id)
    assert not foo.tag_names, 'Tag should have been found by ID.'


@pytest.mark.parametrize('method,suffix', [
    ('replace_info_json', '.info.json'),
    ('replace_readability_json', '.readability.json'),
])
def test_file_group_replace_json(test_session, make_files_structure, method, suffix):
    """replace_info_json and replace_readability_json create, write, and register JSON files."""
    from wrolpi.common import get_media_directory
    make_files_structure({'video.mp4': 'fake video'})
    fg = FileGroup.from_paths(test_session, get_media_directory() / 'video.mp4')
    test_session.add(fg)
    test_session.flush()

    json_path = get_media_directory() / f'video{suffix}'
    assert not json_path.exists(), 'File should not exist before writing'

    data = {'title': 'Test', 'id': 'abc123'}
    getattr(fg, method)(data)

    # File should exist on disk with formatted JSON.
    assert json_path.is_file()
    assert json.loads(json_path.read_text()) == data

    # File should be tracked in FileGroup.files.
    file_paths = [f['path'] for f in fg.my_files()]
    assert json_path in file_paths


@pytest.mark.parametrize('method,suffix', [
    ('replace_info_json', '.info.json'),
    ('replace_readability_json', '.readability.json'),
])
def test_file_group_update_wrolpi_json(test_session, make_files_structure, method, suffix):
    """FileGroup.update_wrolpi_json adds a 'wrolpi' section to .info.json or .readability.json."""
    from wrolpi.common import get_media_directory
    make_files_structure({'video.mp4': 'fake video'})
    fg = FileGroup.from_paths(test_session, get_media_directory() / 'video.mp4')
    test_session.add(fg)
    test_session.flush()

    # Write initial JSON using the appropriate method.
    getattr(fg, method)({'title': 'Test Video', 'id': 'abc123'})

    fg.update_wrolpi_json({'parent_download_url': 'https://example.com'})

    json_path = get_media_directory() / f'video{suffix}'
    written = json.loads(json_path.read_text())
    assert written['title'] == 'Test Video'
    assert written['wrolpi'] == {'parent_download_url': 'https://example.com'}


def test_file_group_update_wrolpi_json_noop_no_metadata_json(test_session, make_files_structure):
    """FileGroup.update_wrolpi_json is a no-op when no metadata JSON file exists."""
    from wrolpi.common import get_media_directory
    make_files_structure({'video.mp4': 'fake video'})
    fg = FileGroup.from_paths(test_session, get_media_directory() / 'video.mp4')
    test_session.add(fg)
    test_session.flush()

    # Should not raise, and should not create any file.
    fg.update_wrolpi_json({'key': 'value'})
    assert not (get_media_directory() / 'video.info.json').exists()
    assert not (get_media_directory() / 'video.readability.json').exists()
