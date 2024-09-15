import pytest


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
