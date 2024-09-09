import pytest


@pytest.mark.asyncio
async def test_file_group_move(async_client, test_session, test_directory, video_factory):
    """Any new or renamed files are adopted during FileGroup.move."""
    video = await video_factory(title='video', with_poster_ext='.webp')
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
async def test_file_group_clean_my_files(async_client, test_session, test_directory, video_factory):
    """Any missing files can be cleaned from FileGroup.files using FileGroup.clean_my_files()"""
    video = await video_factory(
        with_video_file=True,
        with_info_json=True,
        with_poster_ext='.jpg',
        with_caption_file=True,
    )
    test_session.commit()

    # Video has three files.
    assert len(video.file_group.my_files()) == 4
    assert {i.suffix for i in video.file_group.my_paths()} == {'.mp4', '.jpg', '.json', '.vtt'}
    assert video.file_group.primary_path.suffix == '.mp4'

    # Missing files are deleted from FileGroup.files.
    video.info_json_path.unlink()
    video.file_group.clean_my_files()
    assert len(video.file_group.my_files()) == 3
    assert {i.suffix for i in video.file_group.my_paths()} == {'.mp4', '.jpg', '.vtt'}
    assert video.file_group.primary_path.suffix == '.mp4'

    # TODO Video record should be cleaned up if video file is deleted.
    video.video_path.unlink()
    video.file_group.clean_my_files()
    assert {i.suffix for i in video.file_group.my_paths()} == {'.jpg', '.vtt'}
    assert video.file_group.primary_path.suffix == '.jpg'

    video.caption_paths[0].unlink()
    video.file_group.clean_my_files()
    assert {i.suffix for i in video.file_group.my_paths()} == {'.jpg'}
    assert video.file_group.primary_path.suffix == '.jpg'

    # FileGroup cannot be empty.
    video.poster_path.unlink()
    with pytest.raises(FileNotFoundError):
        video.file_group.clean_my_files()