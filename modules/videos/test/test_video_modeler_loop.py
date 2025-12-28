"""Test for video_modeler loop to ensure it processes more than one batch.

This test ensures the video_modeler can process more than VIDEO_PROCESSING_LIMIT (20)
files. If the loop logic has an off-by-one error (like using enumerate() with wrong
comparison), the modeler would only process one batch and exit early.
"""
import shutil

import pytest

from modules.videos import video_modeler, VIDEO_PROCESSING_LIMIT
from modules.videos.models import Video
from wrolpi.files.models import FileGroup
from wrolpi.vars import PROJECT_DIR


@pytest.mark.asyncio
async def test_video_modeler_processes_more_than_batch_limit(async_client, test_session, test_directory):
    """
    Test that video_modeler processes MORE than VIDEO_PROCESSING_LIMIT (20) files.

    This test creates 25 video files and verifies that video_modeler
    processes all of them, not just the first batch of 20.

    This catches off-by-one bugs in the loop logic (e.g., using enumerate()
    which is 0-indexed but comparing against the limit incorrectly).
    """
    video_dir = test_directory / 'videos'
    video_dir.mkdir(parents=True)

    # Create more videos than the batch limit
    num_videos = VIDEO_PROCESSING_LIMIT + 5  # 25 videos
    video_paths = []

    for i in range(num_videos):
        video_path = video_dir / f'test_video_{i:03d}.mp4'
        shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', video_path)
        video_paths.append(video_path)

    # Create FileGroups for each video file (simulating what refresh does)
    for video_path in video_paths:
        fg = FileGroup.from_paths(test_session, video_path)
        assert fg.mimetype.startswith('video/')

    test_session.commit()

    # Verify we have the expected number of FileGroups needing deep indexing
    # Two-phase: indexed=True (surface), deep_indexed=False (needs modeler)
    needs_deep_count = test_session.query(FileGroup).filter(
        FileGroup.indexed == True,
        FileGroup.deep_indexed != True,
        FileGroup.mimetype.like('video/%'),
    ).count()
    assert needs_deep_count == num_videos, f"Expected {num_videos} files needing deep indexing, got {needs_deep_count}"

    # Run the video_modeler
    await video_modeler()

    # Count how many Videos were created
    video_count = test_session.query(Video).count()

    # All videos should be created
    assert video_count == num_videos, \
        f"video_modeler should process ALL {num_videos} files, but only processed {video_count}. " \
        f"This may be an off-by-one bug in the loop logic!"

    # Also verify all FileGroups are now deep indexed
    still_needs_deep = test_session.query(FileGroup).filter(
        FileGroup.indexed == True,
        FileGroup.deep_indexed != True,
        FileGroup.mimetype.like('video/%'),
    ).count()
    assert still_needs_deep == 0, \
        f"All video FileGroups should be deep indexed, but {still_needs_deep} remain"
