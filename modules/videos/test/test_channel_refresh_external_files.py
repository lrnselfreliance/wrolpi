"""Tests that Channel.refresh_files() and refresh_collection() detect changes to files
that are associated with the channel but located outside the channel's directory."""
import shutil

import pytest

from modules.videos.models import Channel, Video
from wrolpi.collections import Collection
from wrolpi.collections.lib import refresh_collection
from wrolpi.collections.models import CollectionItem
from wrolpi.common import await_background_tasks
from wrolpi.conftest import await_file_worker
from wrolpi.files.models import FileGroup


@pytest.mark.asyncio
class TestChannelRefreshExternalFiles:

    async def _setup_channel_with_external_video(
            self, test_session, test_directory, video_file_factory, channel_factory, refresh_files):
        """Create a channel with an internal and external video, then delete the external video from disk.

        Returns (channel, internal_video_id, external_video_id, external_path)."""
        channel = channel_factory(name='MyChannel')
        assert channel.directory.is_dir()

        # Create a video inside the channel directory.
        internal_path = channel.directory / 'internal_video.mp4'
        video_file_factory(internal_path)

        # Create a video outside the channel directory.
        external_dir = test_directory / 'videos' / 'other'
        external_dir.mkdir(parents=True, exist_ok=True)
        external_path = external_dir / 'external_video.mp4'
        video_file_factory(external_path)

        # Refresh to index all files and model videos.
        await refresh_files()

        # Verify both videos exist.
        internal_video = test_session.query(Video).join(Video.file_group).filter(
            FileGroup.primary_path == internal_path,
        ).one()
        external_video = test_session.query(Video).join(Video.file_group).filter(
            FileGroup.primary_path == external_path,
        ).one()

        # Assign the external video to the channel.
        external_video.channel_id = channel.id
        test_session.commit()

        internal_video_id = internal_video.id
        external_video_id = external_video.id

        # Verify channel has 2 videos.
        channel_videos = test_session.query(Video).filter_by(channel_id=channel.id).all()
        assert len(channel_videos) == 2, f'Expected 2 channel videos, got {len(channel_videos)}'

        # Delete ALL files for the external video by removing the directory.
        shutil.rmtree(external_dir)
        assert not external_path.exists()

        return channel, internal_video_id, external_video_id, external_path

    def _assert_external_deleted_internal_kept(self, test_session, internal_video_id, external_video_id, external_path):
        """Assert the external video was cleaned up and the internal video remains."""
        test_session.expire_all()

        external_fg = test_session.query(FileGroup).filter_by(primary_path=external_path).one_or_none()
        assert external_fg is None, \
            'External video FileGroup should have been removed after files were deleted from disk'

        external_vid = test_session.query(Video).filter_by(id=external_video_id).one_or_none()
        assert external_vid is None, \
            'External Video record should have been removed after its files were deleted'

        internal_vid = test_session.query(Video).filter_by(id=internal_video_id).one_or_none()
        assert internal_vid is not None, 'Internal video should still exist'

    async def test_channel_refresh_files_detects_deleted_external_video(
            self, async_client, test_session, test_directory, video_file_factory, channel_factory, refresh_files):
        """Channel.refresh_files() should detect and remove an external video whose files were deleted."""
        channel, internal_id, external_id, external_path = await self._setup_channel_with_external_video(
            test_session, test_directory, video_file_factory, channel_factory, refresh_files)

        Channel.refresh_files(channel.id)
        await await_file_worker()
        await await_background_tasks()

        self._assert_external_deleted_internal_kept(test_session, internal_id, external_id, external_path)

    async def test_refresh_collection_detects_deleted_external_video(
            self, async_client, test_session, test_directory, video_file_factory, channel_factory, refresh_files):
        """refresh_collection() should detect and remove an external video whose files were deleted."""
        channel, internal_id, external_id, external_path = await self._setup_channel_with_external_video(
            test_session, test_directory, video_file_factory, channel_factory, refresh_files)

        collection = test_session.query(Collection).filter_by(id=channel.collection_id).one()
        refresh_collection(collection.id)
        await await_file_worker()

        self._assert_external_deleted_internal_kept(test_session, internal_id, external_id, external_path)

    async def test_refresh_collection_detects_deleted_external_collection_item(
            self, async_client, test_session, test_directory, video_file_factory, refresh_files):
        """refresh_collection() should detect and remove an external CollectionItem-linked FileGroup
        whose files were deleted from disk."""
        # Create a generic collection with a directory.
        collection_dir = test_directory / 'my_collection'
        collection_dir.mkdir(parents=True, exist_ok=True)
        collection = Collection(name='MyCollection', directory=collection_dir, kind='simple')
        test_session.add(collection)
        test_session.flush()

        # Create a video inside the collection directory.
        internal_path = collection_dir / 'internal_video.mp4'
        video_file_factory(internal_path)

        # Create a video outside the collection directory.
        external_dir = test_directory / 'elsewhere'
        external_dir.mkdir(parents=True, exist_ok=True)
        external_path = external_dir / 'external_video.mp4'
        video_file_factory(external_path)

        # Refresh to index all files.
        await refresh_files()

        internal_fg = test_session.query(FileGroup).filter_by(primary_path=internal_path).one()
        external_fg = test_session.query(FileGroup).filter_by(primary_path=external_path).one()
        external_fg_id = external_fg.id

        # Link the external FileGroup to the collection via CollectionItem.
        item = CollectionItem(collection_id=collection.id, file_group_id=external_fg.id)
        test_session.add(item)
        test_session.commit()

        # Delete the external files.
        shutil.rmtree(external_dir)
        assert not external_path.exists()

        # Refresh via collection.
        refresh_collection(collection.id)
        await await_file_worker()

        test_session.expire_all()

        external_fg = test_session.query(FileGroup).filter_by(id=external_fg_id).one_or_none()
        assert external_fg is None, \
            'External CollectionItem FileGroup should have been removed after files were deleted from disk'

        internal_fg = test_session.query(FileGroup).filter_by(primary_path=internal_path).one_or_none()
        assert internal_fg is not None, 'Internal FileGroup should still exist'

    async def test_channel_refresh_detects_new_file_in_external_file_group(
            self, async_client, test_session, test_directory, video_file_factory, channel_factory, refresh_files):
        """Channel.refresh_files() should detect a new sibling file added to an external video's FileGroup."""
        channel = channel_factory(name='MyChannel')

        # Create a video outside the channel directory.
        external_dir = test_directory / 'videos' / 'other'
        external_dir.mkdir(parents=True, exist_ok=True)
        external_path = external_dir / 'external_video.mp4'
        video_file_factory(external_path)

        # Refresh to index the video.
        await refresh_files()

        external_video = test_session.query(Video).join(Video.file_group).filter(
            FileGroup.primary_path == external_path,
        ).one()

        # Assign the external video to the channel.
        external_video.channel_id = channel.id
        test_session.commit()

        # Record the initial file count.
        external_fg = external_video.file_group
        initial_file_names = {f['path'] for f in external_fg.files}
        assert 'external_video.mp4' in initial_file_names

        # Add a subtitle file next to the video with the same stem.
        subtitle_path = external_dir / 'external_video.en.vtt'
        subtitle_path.write_text('WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n')

        # Refresh the channel's files.
        Channel.refresh_files(channel.id)
        await await_file_worker()
        await await_background_tasks()

        test_session.expire_all()

        # The FileGroup should now include the subtitle file.
        external_fg = test_session.query(FileGroup).filter_by(primary_path=external_path).one()
        file_names = {f['path'] for f in external_fg.files}
        assert 'external_video.en.vtt' in file_names, \
            f'Subtitle file should have been detected in external FileGroup, got: {file_names}'
        assert 'external_video.mp4' in file_names, 'Original video file should still be present'
        assert external_fg.primary_path == external_path, 'Primary path should still be the .mp4'
