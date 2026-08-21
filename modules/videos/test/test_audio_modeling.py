"""Uploaded audio files must become Videos, and audio playlists must not.

The upload flow (`upsert_file` -> `FileGroup.do_model` -> `Video.can_model`) and the refresh
flow (the batch `video_modeler`) must agree on what a Video is: video/* and audio/*, except
audio playlists.  A FileGroup either path leaves behind must be picked up by the other.
"""
import asyncio
import shutil
from unittest.mock import patch

import pytest

from modules.videos import video_modeler, video_cleanup, VIDEO_PROCESSING_LIMIT
from modules.videos.models import Video, AUDIO_PLAYLIST_MIMETYPES
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


def test_can_model_rejects_every_playlist_mimetype(test_session, test_directory):
    """Every mimetype on the playlist denylist is refused, whatever libmagic detected it from.

    Direct assignment rather than detection: libmagic versions disagree on .pls (text/plain
    here, audio/x-scpls elsewhere), and the denylist must hold wherever audio/* comes back.
    """
    audio = test_directory / 'stations.pls'
    audio.write_text('[playlist]\nFile1=http://example.org/stream\nNumberOfEntries=1\n')
    file_group = FileGroup.from_paths(test_session, audio)
    for mimetype in AUDIO_PLAYLIST_MIMETYPES:
        file_group.mimetype = mimetype
        assert not Video.can_model(file_group), f'{mimetype} must not model as a Video'
    file_group.mimetype = 'audio/flac'
    assert Video.can_model(file_group), 'non-playlist audio must model as a Video'


@pytest.mark.asyncio
async def test_video_modeler_heals_indexed_filegroup_without_video(async_client, test_session,
                                                                   channel_factory):
    """An audio/video FileGroup that is already indexed but has no Video row is still modeled."""
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
    """A playlist wrongly modeled as a Video is unmodeled by cleanup, for every denylisted type."""
    file_groups = []
    for index, mimetype in enumerate(AUDIO_PLAYLIST_MIMETYPES):
        playlist = test_directory / f'stations_{index}.m3u'
        playlist.write_text('#EXTM3U\n#EXTINF:0,WRMI\nhttp://example.org/stream\n')
        file_group = FileGroup.from_paths(test_session, playlist)
        # The wrong historical state: a Video row and model='video' on a playlist.
        file_group.mimetype = mimetype
        file_group.model = 'video'
        file_group.indexed = True
        test_session.add(Video(file_group=file_group, file_group_id=file_group.id))
        file_groups.append(file_group)
    test_session.commit()

    video_cleanup()

    test_session.expire_all()
    assert test_session.query(Video).count() == 0, 'every playlist Video must be deleted'
    assert all(fg.model is None for fg in file_groups), 'every playlist must be unmodeled'


@pytest.mark.asyncio
async def test_video_modeler_terminates_on_persistent_failure(async_client, test_session, test_directory):
    """video_modeler must terminate even when modeling keeps failing before a Video row exists.

    The `Video.id IS NULL` gate keeps matching a file that fails to model; only the per-run
    `failed_ids` guard stops a full batch of such files from being re-selected forever.
    """
    audio_dir = test_directory / 'audio'
    audio_dir.mkdir(parents=True)
    num_files = VIDEO_PROCESSING_LIMIT + 5
    for i in range(num_files):
        path = audio_dir / f'stuck_{i:03d}.mp3'
        shutil.copy(PROJECT_DIR / 'test/big_buck_bunny.mp3', path)
    for path in sorted(audio_dir.iterdir()):
        fg = FileGroup.from_paths(test_session, path)
        fg.indexed = True  # Already indexed, no Video row: only the new gate selects these.
    test_session.commit()

    # _model_video always raises without persisting a Video row.  PYTEST re-raises inside the
    # loop's per-item handler; disable that to exercise the failure path and the termination
    # guard, not the re-raise.
    with patch('modules.videos._model_video', side_effect=RuntimeError('boom')), \
            patch('modules.videos.PYTEST', False):
        await asyncio.wait_for(video_modeler(), timeout=10)

    assert test_session.query(Video).count() == 0, 'every attempt failed, yet the loop terminated'
