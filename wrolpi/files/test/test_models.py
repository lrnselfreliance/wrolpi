import pytest

from wrolpi.files import lib
from wrolpi.files.models import FileGroup


@pytest.mark.asyncio
async def test_file_group_move(async_client, test_session, test_directory, video_factory):
    """Any new or renamed files are adopted during FileGroup.move."""
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
async def test_add_tag_overload(async_client, test_session, make_files_structure, tag_factory):
    """FileGroup.add_tag and FileGroup.untag use `singeldispatch`."""
    make_files_structure({'foo.txt': 'foo contents'})
    await lib.refresh_files()
    foo: FileGroup = test_session.query(FileGroup).one()

    one, two = await tag_factory(), await tag_factory()

    foo.add_tag(one.name)
    assert set(foo.tag_names) == {'one'}, 'Tag should have been found by name'
    foo.add_tag(two.id)
    assert set(foo.tag_names) == {'one', 'two'}, 'Tag should have been found by ID.'

    foo.untag(one.name)
    assert set(foo.tag_names) == {'two'}, 'Tag should have been found by name'
    foo.untag(two.id)
    assert not foo.tag_names, 'Tag should have been found by ID.'
