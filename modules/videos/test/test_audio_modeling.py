"""Uploaded audio files must become Videos, and audio playlists must not.

The upload flow (`upsert_file` -> `FileGroup.do_model` -> `Video.can_model`) and the refresh
flow (the batch `video_modeler`) must agree on what a Video is.  They did not: the modeler
accepted `audio/%` while `can_model` only accepted `video/%`, so an uploaded .flac was indexed
without a Video row and never appeared in its Channel -- and could never recover, because the
modeler only looked at `indexed != True`.
"""
import shutil

import pytest

from modules.videos import video_modeler, video_cleanup
from modules.videos.models import Video
from wrolpi.files.lib import upsert_file
from wrolpi.files.models import FileGroup
from wrolpi.vars import PROJECT_DIR


@pytest.mark.asyncio
async def test_uploaded_audio_becomes_a_channel_video(async_client, test_session, channel_factory):
    """An audio file uploaded into a Channel's directory is a Video of that Channel."""
    channel = channel_factory(name='The Tech Prepper')
    audio_path = channel.directory / 'interview.mp3'
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny.mp3', audio_path)

    await upsert_file(audio_path)

    file_group = test_session.query(FileGroup).filter_by(primary_path=str(audio_path)).one()
    assert file_group.mimetype.startswith('audio/'), 'the file under test must be audio'
    assert file_group.model == 'video', 'uploaded audio must be modeled as a Video'
    video = test_session.query(Video).filter_by(file_group_id=file_group.id).one()
    assert video.channel_id == channel.id, 'the Video must belong to the Channel it was uploaded into'


@pytest.mark.asyncio
async def test_audio_playlist_is_not_a_video(async_client, test_session, test_directory):
    """An .m3u playlist carries an audio/* mimetype but is a text list of URLs, not media.

    Neither the upload flow nor the batch modeler may turn one into a Video.
    """
    playlist = test_directory / 'stations.m3u'
    playlist.write_text('#EXTM3U\n#EXTINF:0,WRMI\nhttp://example.org/stream\n')

    await upsert_file(playlist)
    await video_modeler()

    file_group = test_session.query(FileGroup).filter_by(primary_path=str(playlist)).one()
    assert file_group.mimetype in ('audio/x-mpegurl', 'audio/mpegurl'), \
        f'the playlist must detect as an audio playlist, got {file_group.mimetype}'
    assert file_group.model is None, 'a playlist must not be modeled'
    assert test_session.query(Video).count() == 0, 'a playlist must not create a Video'


@pytest.mark.asyncio
async def test_video_modeler_heals_indexed_filegroup_without_video(async_client, test_session,
                                                                   channel_factory):
    """An audio/video FileGroup that is already indexed but has no Video row is still modeled.

    Regression: an uploaded .flac was stamped `indexed=True` by the upload flow without a Video
    row, and the modeler's `indexed != True` gate then excluded it on every later refresh --
    the file was stuck invisible in its Channel forever.
    """
    channel = channel_factory(name='The Tech Prepper')
    audio_path = channel.directory / 'stuck.mp3'
    shutil.copy(PROJECT_DIR / 'test/big_buck_bunny.mp3', audio_path)

    # The stuck production state: indexed, no model, no Video row.
    file_group = FileGroup.from_paths(test_session, audio_path)
    file_group.indexed = True
    file_group.model = None
    test_session.commit()

    await video_modeler()

    test_session.expire_all()
    video = test_session.query(Video).filter_by(file_group_id=file_group.id).one()
    assert file_group.model == 'video'
    assert video.channel_id == channel.id, 'the healed Video must be claimed by its Channel'


@pytest.mark.asyncio
async def test_video_cleanup_unmodels_playlists(async_client, test_session, test_directory):
    """A playlist that an older modeler wrongly turned into a Video is unmodeled by cleanup."""
    playlist = test_directory / 'stations.m3u'
    playlist.write_text('#EXTM3U\n#EXTINF:0,WRMI\nhttp://example.org/stream\n')

    file_group = FileGroup.from_paths(test_session, playlist)
    assert file_group.mimetype in ('audio/x-mpegurl', 'audio/mpegurl')
    # The wrong historical state: a Video row and model='video' on a playlist.
    video = Video(file_group=file_group, file_group_id=file_group.id)
    test_session.add(video)
    file_group.model = 'video'
    file_group.indexed = True
    test_session.commit()

    video_cleanup()

    test_session.expire_all()
    assert test_session.query(Video).count() == 0, 'the playlist Video must be deleted'
    assert file_group.model is None, 'the playlist must be unmodeled'
