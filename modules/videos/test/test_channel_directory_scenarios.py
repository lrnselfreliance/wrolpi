"""
Tests for channel directory detection scenarios, specifically around directory detection
when videos are organized in year subdirectories.

These tests expose bugs where:
1. Video.validate() uses exact directory match, failing for year subdirectories
2. Videos in year subdirs don't get channel's generate_posters setting applied
3. Channel.get_by_path() returns None for paths in subdirectories

These tests use the REAL modeling flow:
1. Create video files on disk in year subdirectories
2. Create channel with directory at parent level
3. Run refresh_files() to trigger video modeling
4. Verify the video is correctly associated with the channel
"""

import pytest

from modules.videos.models import Channel, Video
from wrolpi.collections import Collection


@pytest.mark.asyncio
class TestNonTaggedChannelDirectoryDetection:
    """Tests that non-tagged channel directories work correctly."""

    async def test_video_association_non_tagged_channel(
            self, async_client, test_session, test_directory, video_file, refresh_files):
        """
        Videos in a non-tagged channel directory should be associated with that channel.

        If videos/ChannelName exists and a channel is created with that directory,
        videos within should be associated with the channel.
        """
        # Create a channel WITHOUT a tag
        channel_dir = test_directory / 'videos' / 'SimpleChannel'
        channel_dir.mkdir(parents=True, exist_ok=True)

        collection = Collection(
            name='SimpleChannel',
            kind='channel',
            directory=channel_dir,
            tag_id=None,  # Explicitly no tag
        )
        test_session.add(collection)
        test_session.flush([collection])

        channel = Channel(
            collection_id=collection.id,
            url='https://example.com/simplechannel',
        )
        test_session.add(channel)
        test_session.commit()

        # Verify no tag
        assert channel.tag is None, 'Channel should not have a tag'

        # Create video directly in channel directory (no year subdirectory)
        video_path = channel_dir / 'Simple Video.mp4'
        video_file.rename(video_path)

        await refresh_files()

        # Video should be associated with the non-tagged channel
        video = test_session.query(Video).join(Video.file_group).filter(
            Video.file_group.has(primary_path=str(video_path))
        ).one_or_none()

        assert video is not None, 'Video should have been created'
        assert video.channel_id == channel.id, \
            f'Video should be associated with non-tagged channel, got channel_id={video.channel_id}'
        assert video.channel.tag is None, 'Channel should still have no tag'

    async def test_video_association_non_tagged_channel_nested_directory(
            self, async_client, test_session, test_directory, video_file, refresh_files):
        """
        Videos in nested directories under a non-tagged channel should be associated.

        If videos/ChannelName/subdir exists, videos there should be associated
        with the channel at videos/ChannelName.
        """
        # Create a channel WITHOUT a tag
        channel_dir = test_directory / 'videos' / 'NestedChannel'
        channel_dir.mkdir(parents=True, exist_ok=True)

        collection = Collection(
            name='NestedChannel',
            kind='channel',
            directory=channel_dir,
            tag_id=None,
        )
        test_session.add(collection)
        test_session.flush([collection])

        channel = Channel(
            collection_id=collection.id,
            url='https://example.com/nestedchannel',
        )
        test_session.add(channel)
        test_session.commit()

        # Create video in a nested subdirectory
        nested_dir = channel_dir / 'season1' / 'episode1'
        nested_dir.mkdir(parents=True, exist_ok=True)
        video_path = nested_dir / 'Nested Video.mp4'
        video_file.rename(video_path)

        await refresh_files()

        # Video should be associated with the channel even in nested subdirectory
        video = test_session.query(Video).join(Video.file_group).filter(
            Video.file_group.has(primary_path=str(video_path))
        ).one_or_none()

        assert video is not None
        # Note: This may fail if video_cleanup doesn't run or if the LIKE clause doesn't match
        assert video.channel_id == channel.id, \
            f'Video in nested directory should be associated with channel, got channel_id={video.channel_id}'

    async def test_channel_created_after_videos_non_tagged(
            self, async_client, test_session, test_directory, video_file,
            test_channels_config, refresh_files):
        """
        When a non-tagged channel is created via config import AFTER videos exist,
        the videos should be claimed by the channel.
        """
        import yaml
        from modules.videos.lib import get_channels_config

        # Create video BEFORE channel exists
        videos_dir = test_directory / 'videos' / 'LateNonTaggedChannel'
        videos_dir.mkdir(parents=True, exist_ok=True)
        video_path = videos_dir / 'Early Video.mp4'
        video_file.rename(video_path)

        await refresh_files()

        # Video exists but has no channel
        video = test_session.query(Video).join(Video.file_group).filter(
            Video.file_group.has(primary_path=str(video_path))
        ).one_or_none()
        assert video is not None
        assert video.channel_id is None, 'Video should not have channel before config import'

        # Now import channel config (non-tagged channel)
        config = get_channels_config()
        config_path = config.get_file()

        config_data = {
            'version': 0,
            'channels': [{
                'name': 'LateNonTaggedChannel',
                'directory': str(videos_dir),
                'url': 'https://example.com/latenontagged',
                # Note: no tag_name field = non-tagged channel
            }]
        }
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        config.initialize()
        config.import_config()

        # Refresh video from DB
        test_session.expire(video)

        # Video should now be claimed by the non-tagged channel
        assert video.channel_id is not None, \
            'Video should be claimed by non-tagged channel after config import'

        channel = test_session.query(Channel).join(Collection).filter(
            Collection.name == 'LateNonTaggedChannel'
        ).one()
        assert video.channel_id == channel.id
        assert channel.tag is None, 'Channel should be non-tagged'


@pytest.mark.asyncio
class TestVideoModelingWithYearSubdirs:
    """Tests using real video modeling flow with year subdirectories."""

    async def test_video_modeling_year_subdirectory_detection(
            self, async_client, test_session, test_directory, video_file, refresh_files):
        """
        Bug test: When videos are in year subdirectories, the video
        should be associated with the channel at the parent directory.

        Uses real refresh flow to trigger video modeling.
        """
        # Create channel with directory at videos/TestChannel
        channel_dir = test_directory / 'videos' / 'TestChannel'
        channel_dir.mkdir(parents=True, exist_ok=True)

        collection = Collection(
            name='TestChannel',
            kind='channel',
            directory=channel_dir,
        )
        test_session.add(collection)
        test_session.flush([collection])

        channel = Channel(
            collection_id=collection.id,
            url='https://example.com/testchannel',
        )
        test_session.add(channel)
        test_session.commit()

        # Create video file in year subdirectory
        year_dir = channel_dir / '2026'
        year_dir.mkdir(parents=True, exist_ok=True)
        video_path = year_dir / '2026-01-01_Test Video.mp4'
        video_file.rename(video_path)

        # Run file refresh - this triggers video modeling
        await refresh_files()

        # Verify video was created
        video = test_session.query(Video).join(Video.file_group).filter(
            Video.file_group.has(primary_path=str(video_path))
        ).one_or_none()
        assert video is not None, 'Video should have been created'

        # BUG: Video.validate() uses Channel.get_by_path() with exact match
        # This fails because video_path.parent is videos/TestChannel/2026
        # but channel.directory is videos/TestChannel
        assert video.channel_id is not None, \
            f'Video should be associated with channel, but channel_id is None. Video path: {video_path}'
        assert video.channel_id == channel.id, \
            f'Video should be associated with TestChannel, got channel_id={video.channel_id}'

    async def test_video_modeling_multiple_year_subdirectories(
            self, async_client, test_session, test_directory, video_file_factory, refresh_files):
        """
        When videos span multiple years, they should all be associated
        with the same channel at the parent directory.
        """
        # Create channel
        channel_dir = test_directory / 'videos' / 'MultiYearChannel'
        channel_dir.mkdir(parents=True, exist_ok=True)

        collection = Collection(
            name='MultiYearChannel',
            kind='channel',
            directory=channel_dir,
        )
        test_session.add(collection)
        test_session.flush([collection])

        channel = Channel(
            collection_id=collection.id,
            url='https://example.com/multiyear',
        )
        test_session.add(channel)
        test_session.commit()

        # Create videos in different year subdirectories
        year_2025 = channel_dir / '2025'
        year_2026 = channel_dir / '2026'
        year_2025.mkdir(parents=True, exist_ok=True)
        year_2026.mkdir(parents=True, exist_ok=True)

        video_path_2025 = year_2025 / '2025-06-01_Old Video.mp4'
        video_path_2026 = year_2026 / '2026-01-01_New Video.mp4'

        video_file_factory(video_path_2025)
        video_file_factory(video_path_2026)

        await refresh_files()

        # Both videos should be associated with the same channel
        video_2025 = test_session.query(Video).join(Video.file_group).filter(
            Video.file_group.has(primary_path=str(video_path_2025))
        ).one_or_none()
        video_2026 = test_session.query(Video).join(Video.file_group).filter(
            Video.file_group.has(primary_path=str(video_path_2026))
        ).one_or_none()

        assert video_2025 is not None
        assert video_2026 is not None

        # BUG: Both videos should belong to the channel
        assert video_2025.channel_id == channel.id, \
            f'2025 video should be in channel, got channel_id={video_2025.channel_id}'
        assert video_2026.channel_id == channel.id, \
            f'2026 video should be in channel, got channel_id={video_2026.channel_id}'

    async def test_video_modeling_tagged_channel_with_year_subdirs(
            self, async_client, test_session, test_directory, video_file,
            test_tags_config, refresh_files):
        """
        For tagged channels, videos in year subdirectories should still
        be associated with the channel.

        Channel at: videos/education/TechChannel
        Video at: videos/education/TechChannel/2026/video.mp4
        """
        from wrolpi import tags

        # Create tag
        config_dir = test_directory / 'config'
        config_dir.mkdir(exist_ok=True)
        test_tags_config.write_text('''
version: 0
tags:
  education:
    color: '#00FF00'
''')
        tags.import_tags_config()

        # Get the tag
        from wrolpi.tags import Tag
        edu_tag = test_session.query(Tag).filter_by(name='education').one()

        # Create channel with tag
        channel_dir = test_directory / 'videos' / 'education' / 'TechChannel'
        channel_dir.mkdir(parents=True, exist_ok=True)

        collection = Collection(
            name='TechChannel',
            kind='channel',
            directory=channel_dir,
            tag_id=edu_tag.id,
        )
        test_session.add(collection)
        test_session.flush([collection])

        channel = Channel(
            collection_id=collection.id,
            url='https://example.com/techchannel',
        )
        test_session.add(channel)
        test_session.commit()

        # Create video in year subdirectory
        year_dir = channel_dir / '2026'
        year_dir.mkdir(parents=True, exist_ok=True)
        video_path = year_dir / '2026-01-01_Tagged Video.mp4'
        video_file.rename(video_path)

        await refresh_files()

        # Verify video was associated with tagged channel
        video = test_session.query(Video).join(Video.file_group).filter(
            Video.file_group.has(primary_path=str(video_path))
        ).one_or_none()

        assert video is not None
        assert video.channel_id == channel.id, \
            f'Video should be associated with tagged channel, got channel_id={video.channel_id}'
        assert video.channel.tag_name == 'education', \
            f'Channel should have education tag, got {video.channel.tag_name}'


@pytest.mark.asyncio
class TestGeneratePostersWithYearSubdirs:
    """Tests for generate_posters setting with year subdirectories."""

    async def test_generate_posters_year_subdirectory(
            self, async_client, test_session, test_directory, video_file, refresh_files):
        """
        Bug test: When videos are in year subdirectories, the channel's
        generate_posters setting should still be applied.

        Currently fails because Video.validate() can't find the channel
        (exact directory match), so generate_posters defaults to False.
        """
        # Create channel with generate_posters=True
        channel_dir = test_directory / 'videos' / 'PosterChannel'
        channel_dir.mkdir(parents=True, exist_ok=True)

        collection = Collection(
            name='PosterChannel',
            kind='channel',
            directory=channel_dir,
        )
        test_session.add(collection)
        test_session.flush([collection])

        channel = Channel(
            collection_id=collection.id,
            url='https://example.com/posterchannel',
            generate_posters=True,
        )
        test_session.add(channel)
        test_session.commit()

        # Create video in year subdirectory
        year_dir = channel_dir / '2026'
        year_dir.mkdir(parents=True, exist_ok=True)
        video_path = year_dir / '2026-01-01_Poster Video.mp4'
        video_file.rename(video_path)

        await refresh_files()

        video = test_session.query(Video).join(Video.file_group).filter(
            Video.file_group.has(primary_path=str(video_path))
        ).one_or_none()

        assert video is not None
        # BUG: Video should be in channel with generate_posters=True
        # But validate() can't find channel, so posters won't be generated
        assert video.channel_id == channel.id, \
            f'Video should be in channel to get generate_posters setting, got channel_id={video.channel_id}'

    async def test_generate_posters_timing_issue(
            self, async_client, test_session, test_directory, video_file, refresh_files):
        """
        Bug test: Poster generation happens DURING validate_video(),
        but channel association happens AFTER via video_cleanup().

        This means videos in year subdirectories don't get posters
        generated even when channel.generate_posters=True.

        The channel is found at validation time only via:
        1. get_channel(directory=video_path.parent) - exact match, fails for subdirs
        2. Channel.get_by_path(video_path.parent) - exact match, fails for subdirs

        Both use exact directory matching which doesn't handle subdirectories.
        """
        # Create channel with generate_posters=True
        channel_dir = test_directory / 'videos' / 'TimingChannel'
        channel_dir.mkdir(parents=True, exist_ok=True)

        collection = Collection(
            name='TimingChannel',
            kind='channel',
            directory=channel_dir,
        )
        test_session.add(collection)
        test_session.flush([collection])

        channel = Channel(
            collection_id=collection.id,
            url='https://example.com/timingchannel',
            generate_posters=True,  # Should generate posters
        )
        test_session.add(channel)
        test_session.commit()

        # Create video in year subdirectory (WITHOUT existing poster)
        year_dir = channel_dir / '2026'
        year_dir.mkdir(parents=True, exist_ok=True)
        video_path = year_dir / '2026-01-01_No Poster Video.mp4'
        video_file.rename(video_path)

        # Verify no poster exists before refresh
        expected_poster = video_path.with_suffix('.jpg')
        assert not expected_poster.exists(), 'Poster should not exist before refresh'

        await refresh_files()

        video = test_session.query(Video).join(Video.file_group).filter(
            Video.file_group.has(primary_path=str(video_path))
        ).one_or_none()

        assert video is not None
        assert video.channel_id == channel.id, 'Video should be in channel after cleanup'
        assert video.channel.generate_posters is True, 'Channel should have generate_posters=True'

        # BUG: Poster should have been generated because channel.generate_posters=True
        # But during validate_video(), channel wasn't found (exact match failed),
        # so generate_posters defaulted to False and poster wasn't generated.
        # By the time video_cleanup() assigns the channel, validation is already done.
        assert video.poster_path is not None, \
            'Poster should have been generated because channel.generate_posters=True'


@pytest.mark.asyncio
class TestChannelGetByPathWithSubdirs:
    """Tests for Channel.get_by_path() with subdirectories."""

    async def test_get_by_path_exact_match(
            self, async_client, test_session, test_directory):
        """
        Channel.get_by_path() should find channel with exact directory match.
        This is the current expected behavior.
        """
        channel_dir = test_directory / 'videos' / 'ExactChannel'
        channel_dir.mkdir(parents=True, exist_ok=True)

        collection = Collection(
            name='ExactChannel',
            kind='channel',
            directory=channel_dir,
        )
        test_session.add(collection)
        test_session.flush([collection])

        channel = Channel(
            collection_id=collection.id,
            url='https://example.com/exactchannel',
        )
        test_session.add(channel)
        test_session.commit()

        # Exact match should work
        found_channel = Channel.get_by_path(test_session, channel_dir)
        assert found_channel is not None
        assert found_channel.id == channel.id

    async def test_get_by_path_year_subdirectory_fails(
            self, async_client, test_session, test_directory):
        """
        Bug demonstration: Channel.get_by_path() with year subdirectory
        returns None because it uses exact match.

        This is the root cause of videos in year subdirs not being
        associated with their channels during validate().
        """
        channel_dir = test_directory / 'videos' / 'SubdirChannel'
        channel_dir.mkdir(parents=True, exist_ok=True)

        collection = Collection(
            name='SubdirChannel',
            kind='channel',
            directory=channel_dir,
        )
        test_session.add(collection)
        test_session.flush([collection])

        channel = Channel(
            collection_id=collection.id,
            url='https://example.com/subdirchannel',
        )
        test_session.add(channel)
        test_session.commit()

        # Year subdirectory lookup should find the parent channel
        year_dir = channel_dir / '2026'
        year_dir.mkdir(parents=True, exist_ok=True)

        # BUG: This returns None because Channel.get_by_path uses exact match
        found_channel = Channel.get_by_path(test_session, year_dir)
        # Current behavior: returns None
        # Expected behavior: should find channel at parent directory
        assert found_channel is not None, \
            'Channel.get_by_path should find channel for year subdirectory'
        assert found_channel.id == channel.id


@pytest.mark.asyncio
class TestGetChannelWithSubdirs:
    """Tests for get_channel() function with subdirectories."""

    async def test_get_channel_by_directory_exact_match(
            self, async_client, test_session, test_directory):
        """
        get_channel() with directory param finds channel with exact match.
        """
        from modules.videos.channel.lib import get_channel

        channel_dir = test_directory / 'videos' / 'GetChannelExact'
        channel_dir.mkdir(parents=True, exist_ok=True)

        collection = Collection(
            name='GetChannelExact',
            kind='channel',
            directory=channel_dir,
        )
        test_session.add(collection)
        test_session.flush([collection])

        channel = Channel(
            collection_id=collection.id,
            url='https://example.com/getchannelexact',
        )
        test_session.add(channel)
        test_session.commit()

        # Exact match should work
        found_channel = get_channel(test_session, directory=str(channel_dir), return_dict=False)
        assert found_channel is not None
        assert found_channel.id == channel.id

    async def test_get_channel_by_directory_year_subdirectory_fails(
            self, async_client, test_session, test_directory):
        """
        Bug demonstration: get_channel() with directory param returns None
        for year subdirectories because it uses exact match.

        This is called from validate_video() at line 122:
            directory=video.video_path.parent

        For videos in year subdirs, video_path.parent is the year subdir,
        not the channel's root directory.
        """
        from modules.videos.channel.lib import get_channel
        from modules.videos.errors import UnknownChannel

        channel_dir = test_directory / 'videos' / 'GetChannelSubdir'
        channel_dir.mkdir(parents=True, exist_ok=True)

        collection = Collection(
            name='GetChannelSubdir',
            kind='channel',
            directory=channel_dir,
        )
        test_session.add(collection)
        test_session.flush([collection])

        channel = Channel(
            collection_id=collection.id,
            url='https://example.com/getchannelsubdir',
        )
        test_session.add(channel)
        test_session.commit()

        # Year subdirectory lookup
        year_dir = channel_dir / '2026'
        year_dir.mkdir(parents=True, exist_ok=True)

        # BUG: This raises UnknownChannel because get_channel uses exact match
        # Expected: should find channel at parent directory
        try:
            found_channel = get_channel(test_session, directory=str(year_dir), return_dict=False)
            assert found_channel is not None, \
                'get_channel should find channel for year subdirectory'
            assert found_channel.id == channel.id
        except UnknownChannel:
            # This is the current buggy behavior - it raises UnknownChannel
            pytest.fail('get_channel should find channel for year subdirectory, but raised UnknownChannel')


@pytest.mark.asyncio
class TestConfigImportThenVideoModeling:
    """Tests for config import followed by video modeling."""

    async def test_config_import_then_video_modeling(
            self, async_client, test_session, test_directory, video_file,
            test_channels_config, refresh_files):
        """
        Test full flow:
        1. Import channels config (creates channel)
        2. Create video files on disk in year subdirectory
        3. Run refresh (triggers modeling)
        4. Verify video is correctly associated with channel
        """
        import yaml
        from modules.videos.lib import get_channels_config

        config = get_channels_config()
        config_path = config.get_file()

        # Create channel directory
        channel_dir = test_directory / 'videos' / 'ConfigChannel'
        channel_dir.mkdir(parents=True, exist_ok=True)

        # Write channels config
        config_data = {
            'version': 0,
            'channels': [{
                'name': 'ConfigChannel',
                'directory': str(channel_dir),
                'url': 'https://example.com/configchannel',
            }]
        }
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        # Import config
        config.initialize()
        config.import_config()

        # Verify channel was created
        channel = test_session.query(Channel).join(Collection).filter(
            Collection.name == 'ConfigChannel'
        ).one_or_none()
        assert channel is not None

        # Create video in year subdirectory
        year_dir = channel_dir / '2026'
        year_dir.mkdir(parents=True, exist_ok=True)
        video_path = year_dir / '2026-01-01_Config Video.mp4'
        video_file.rename(video_path)

        # Run refresh to trigger video modeling
        await refresh_files()

        # Video should be associated with channel
        video = test_session.query(Video).join(Video.file_group).filter(
            Video.file_group.has(primary_path=str(video_path))
        ).one_or_none()

        assert video is not None
        # This might pass because claim_videos_for_channels() runs after import
        # But if it runs during validate(), it will fail
        assert video.channel_id == channel.id, \
            f'Video should be associated with channel after config import, got channel_id={video.channel_id}'

    async def test_video_before_config_import(
            self, async_client, test_session, test_directory, video_file,
            test_channels_config, refresh_files):
        """
        Test when videos exist before channel config is imported.
        1. Create video files in year subdirectory
        2. Run refresh (video gets modeled without channel)
        3. Import channels config
        4. Verify video gets associated with channel via claim_videos_for_channels
        """
        import yaml
        from modules.videos.lib import get_channels_config

        # Create video in what will be the channel's year subdirectory
        channel_dir = test_directory / 'videos' / 'LateChannel'
        year_dir = channel_dir / '2026'
        year_dir.mkdir(parents=True, exist_ok=True)
        video_path = year_dir / '2026-01-01_Early Video.mp4'
        video_file.rename(video_path)

        # Run refresh BEFORE channel config import
        await refresh_files()

        # Video exists but has no channel
        video = test_session.query(Video).join(Video.file_group).filter(
            Video.file_group.has(primary_path=str(video_path))
        ).one_or_none()
        assert video is not None
        assert video.channel_id is None, 'Video should not have channel before config import'

        # Now import channel config
        config = get_channels_config()
        config_path = config.get_file()

        config_data = {
            'version': 0,
            'channels': [{
                'name': 'LateChannel',
                'directory': str(channel_dir),
                'url': 'https://example.com/latechannel',
            }]
        }
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        config.initialize()
        config.import_config()

        # Refresh video from DB
        test_session.expire(video)

        # Video should now be associated with channel via claim_videos_for_channels
        assert video.channel_id is not None, \
            'Video should be claimed by channel after config import'

        channel = test_session.query(Channel).join(Collection).filter(
            Collection.name == 'LateChannel'
        ).one()
        assert video.channel_id == channel.id


@pytest.mark.asyncio
class TestVideoCleanupWithYearSubdirs:
    """Tests for video_cleanup() handling of year subdirectories."""

    async def test_video_cleanup_claims_videos_in_year_subdirs(
            self, async_client, test_session, test_directory, video_file, refresh_files):
        """
        Test that video_cleanup() correctly claims videos in year subdirectories.

        video_cleanup uses SQL with LIKE clause which should handle subdirs:
        fg.directory LIKE col.directory || '/%'
        """
        from modules.videos import video_cleanup

        # Create channel
        channel_dir = test_directory / 'videos' / 'CleanupChannel'
        channel_dir.mkdir(parents=True, exist_ok=True)

        collection = Collection(
            name='CleanupChannel',
            kind='channel',
            directory=channel_dir,
        )
        test_session.add(collection)
        test_session.flush([collection])

        channel = Channel(
            collection_id=collection.id,
            url='https://example.com/cleanupchannel',
        )
        test_session.add(channel)
        test_session.commit()

        # Create video in year subdirectory
        year_dir = channel_dir / '2026'
        year_dir.mkdir(parents=True, exist_ok=True)
        video_path = year_dir / '2026-01-01_Cleanup Video.mp4'
        video_file.rename(video_path)

        # Run refresh to create video record
        await refresh_files()

        video = test_session.query(Video).join(Video.file_group).filter(
            Video.file_group.has(primary_path=str(video_path))
        ).one_or_none()
        assert video is not None

        # Note: After refresh, video.channel_id might already be set
        # if claim_videos_for_channels ran. Let's clear it to test video_cleanup
        video.channel_id = None
        test_session.commit()

        # Run video_cleanup
        video_cleanup()

        # Refresh from DB
        test_session.expire(video)

        # video_cleanup should claim the video via LIKE clause
        assert video.channel_id == channel.id, \
            f'video_cleanup should claim video in year subdir, got channel_id={video.channel_id}'
