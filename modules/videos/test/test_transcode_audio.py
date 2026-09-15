"""Audio-only transcodes: removing the video stream from a video, and transcoding audio files."""
import json
import pathlib
import shutil
from unittest import mock

import pytest

from modules.videos.transcode import transcode_video_file, validate_transcode_request, verify_transcode_output, \
    REMOVE_VIDEO, TRANSCODE_AUDIO_CONTAINERS, default_audio_container, transcode_video_job
from wrolpi import jobs
from wrolpi.cmd import CommandResult
from wrolpi.vars import PROJECT_DIR

MP4 = 'mov,mp4,m4a,3gp,3g2,mj2'


def make_probe(vcodec, acodec, duration=10.0, format_name=MP4):
    streams = []
    if vcodec:
        streams.append({'codec_type': 'video', 'codec_name': vcodec})
    if acodec:
        streams.append({'codec_type': 'audio', 'codec_name': acodec})
    return {'streams': streams, 'format': {'format_name': format_name, 'duration': str(duration)}}


class FakeProbes:
    def __init__(self, source, output):
        self.source, self.output = source, output

    def __call__(self, path: pathlib.Path):
        return self.output if '.transcode.' in path.name else self.source


def fake_ffmpeg(cmd, **kwargs):
    """Writes the output file; the tail-decode check writes nothing."""
    if cmd[-1] != '-':
        pathlib.Path(cmd[-1]).write_bytes(b'output data')
    return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)


async def async_fake_ffmpeg(cmd, **kwargs):
    return fake_ffmpeg(cmd, **kwargs)


# ------------------------------------------------------------------ validation

def test_validate_remove_video():
    """Removing the video needs an audio container; an audio container needs a compatible codec."""
    validate_transcode_request(REMOVE_VIDEO, 'aac', 'm4a')
    validate_transcode_request(REMOVE_VIDEO, None, 'ogg')  # Copy: checked against the source later.
    validate_transcode_request(REMOVE_VIDEO, 'mp3', 'mp3')
    with pytest.raises(ValueError, match='audio container'):
        validate_transcode_request(REMOVE_VIDEO, 'aac', 'mp4')
    with pytest.raises(ValueError, match='ogg'):
        validate_transcode_request(REMOVE_VIDEO, 'aac', 'ogg')
    with pytest.raises(ValueError, match='mp3'):
        validate_transcode_request(REMOVE_VIDEO, 'opus', 'mp3')
    with pytest.raises(ValueError, match='video'):
        validate_transcode_request('h264', 'aac', 'm4a')  # A video stream cannot live in m4a.
    assert set(TRANSCODE_AUDIO_CONTAINERS) == {'m4a', 'ogg', 'mp3'}


def test_default_audio_container():
    assert default_audio_container('aac') == 'm4a'
    assert default_audio_container('opus') == 'ogg'
    assert default_audio_container('vorbis') == 'ogg'
    assert default_audio_container('mp3') == 'mp3'
    assert default_audio_container('flac') == 'ogg'
    assert default_audio_container(None) == 'm4a'


# ------------------------------------------------------------------ verification

def test_verify_audio_only_output():
    source = make_probe('vp9', 'opus', 100.0, 'matroska,webm')
    good = make_probe(None, 'aac', 100.0)
    verify_transcode_output(source, good, REMOVE_VIDEO, 'aac', 'm4a')
    # The video stream must be gone.
    with pytest.raises(RuntimeError, match='video stream'):
        verify_transcode_output(source, make_probe('vp9', 'aac', 100.0), REMOVE_VIDEO, 'aac', 'm4a')
    # An embedded cover is not a video stream.
    verify_transcode_output(source, make_probe('mjpeg', 'aac', 100.0), REMOVE_VIDEO, 'aac', 'm4a')
    # Audio is required.
    with pytest.raises(RuntimeError, match='audio'):
        verify_transcode_output(source, make_probe(None, None, 100.0), REMOVE_VIDEO, 'aac', 'm4a')


def test_verify_container_names():
    """ffprobe names containers differently than the file suffix does."""
    source = make_probe('h264', 'aac', 10.0)
    verify_transcode_output(source, make_probe('h264', 'aac', 10.0, 'matroska,webm'), None, None, 'mkv')
    verify_transcode_output(source, make_probe(None, 'opus', 10.0, 'ogg'), REMOVE_VIDEO, 'opus', 'ogg')
    verify_transcode_output(source, make_probe(None, 'mp3', 10.0, 'mp3'), REMOVE_VIDEO, 'mp3', 'mp3')
    verify_transcode_output(source, make_probe(None, 'aac', 10.0, MP4), REMOVE_VIDEO, None, 'm4a')
    with pytest.raises(RuntimeError, match='container'):
        verify_transcode_output(source, make_probe(None, 'mp3', 10.0, 'mp3'), REMOVE_VIDEO, 'mp3', 'ogg')


def test_verify_audio_source():
    """An audio-only source has no video to demand; the output is audio-only too."""
    source = make_probe(None, 'mp3', 100.0, 'mp3')
    verify_transcode_output(source, make_probe(None, 'aac', 100.0), None, 'aac', 'm4a')
    verify_transcode_output(source, make_probe(None, 'mp3', 100.0, 'mp3'), None, None, 'mp3')


# ------------------------------------------------------------------ transcode_video_file

@pytest.mark.asyncio
async def test_remove_video(test_directory, async_client):
    """Removing the video: no video map, `-vn`, the audio is required, the output is an audio file
    named for its container, and the original is replaced."""
    video_path = test_directory / 'movie.mp4'
    video_path.write_bytes(b'fake video data')
    probes = FakeProbes(make_probe('h264', 'aac', 10.0), make_probe(None, 'aac', 10.0))

    with mock.patch('modules.videos.transcode.probe_for_verify', side_effect=probes), \
            mock.patch('modules.videos.transcode.run_command', side_effect=async_fake_ffmpeg) as mock_run:
        result = await transcode_video_file(video_path, target_vcodec=REMOVE_VIDEO, target_acodec=None,
                                            container='m4a')

    assert result == test_directory / 'movie.m4a' and result.is_file()
    assert not video_path.exists()
    cmd = mock_run.call_args_list[0][0][0]
    assert '-vn' in cmd
    assert '0:V:0' not in cmd
    assert cmd[cmd.index('-map') + 1] == '0:a:0', 'Audio is required, not optional'
    assert '-c:v' not in cmd
    assert cmd[cmd.index('-c:a') + 1] == 'copy'
    assert '+faststart' in cmd, 'm4a is an mp4; fast start applies'
    assert str(cmd[-1]).endswith('movie.transcode.m4a')


@pytest.mark.asyncio
async def test_remove_video_to_ogg_no_faststart(test_directory, async_client):
    video_path = test_directory / 'movie.webm'
    video_path.write_bytes(b'fake video data')
    probes = FakeProbes(make_probe('vp9', 'opus', 10.0, 'matroska,webm'), make_probe(None, 'opus', 10.0, 'ogg'))

    with mock.patch('modules.videos.transcode.probe_for_verify', side_effect=probes), \
            mock.patch('modules.videos.transcode.run_command', side_effect=async_fake_ffmpeg) as mock_run:
        result = await transcode_video_file(video_path, target_vcodec=REMOVE_VIDEO, container='ogg')

    assert result == test_directory / 'movie.ogg'
    cmd = mock_run.call_args_list[0][0][0]
    assert '-movflags' not in cmd, 'movflags is an mp4 muxer option'


@pytest.mark.asyncio
async def test_audio_source_is_audio_output(test_directory, async_client):
    """An audio file has no video to keep or remove: the output is audio-only whatever the video
    target says, and an unsuitable container is replaced by the codec's natural one."""
    audio_path = test_directory / 'song.webm'
    audio_path.write_bytes(b'fake audio data')
    probes = FakeProbes(make_probe(None, 'opus', 10.0, 'matroska,webm'), make_probe(None, 'opus', 10.0, 'ogg'))

    with mock.patch('modules.videos.transcode.probe_for_verify', side_effect=probes), \
            mock.patch('modules.videos.transcode.run_command', side_effect=async_fake_ffmpeg) as mock_run:
        result = await transcode_video_file(audio_path, target_vcodec=None, target_acodec=None, container='mp4')

    assert result == test_directory / 'song.ogg', 'opus copied: ogg, not the video container asked for'
    cmd = mock_run.call_args_list[0][0][0]
    assert '-vn' in cmd and '0:V:0' not in cmd


@pytest.mark.asyncio
async def test_copy_audio_into_incompatible_container_is_refused(test_directory, async_client):
    """Copying opus into m4a cannot work; refuse before ffmpeg runs."""
    video_path = test_directory / 'movie.webm'
    video_path.write_bytes(b'fake video data')
    probes = FakeProbes(make_probe('vp9', 'opus', 10.0, 'matroska,webm'), make_probe(None, 'opus', 10.0))

    with mock.patch('modules.videos.transcode.probe_for_verify', side_effect=probes), \
            mock.patch('modules.videos.transcode.run_command', side_effect=async_fake_ffmpeg) as mock_run:
        with pytest.raises(RuntimeError, match='m4a'):
            await transcode_video_file(video_path, target_vcodec=REMOVE_VIDEO, target_acodec=None, container='m4a')
    mock_run.assert_not_called()
    assert video_path.is_file()


@pytest.mark.asyncio
async def test_video_target_on_audio_source_is_refused(test_directory, async_client):
    audio_path = test_directory / 'song.mp3'
    audio_path.write_bytes(b'fake audio data')
    probes = FakeProbes(make_probe(None, 'mp3', 10.0, 'mp3'), make_probe(None, 'mp3', 10.0, 'mp3'))

    with mock.patch('modules.videos.transcode.probe_for_verify', side_effect=probes), \
            mock.patch('modules.videos.transcode.run_command', side_effect=async_fake_ffmpeg) as mock_run:
        with pytest.raises(RuntimeError, match='no video stream'):
            await transcode_video_file(audio_path, target_vcodec='h264', container='mp4')
    mock_run.assert_not_called()


# ------------------------------------------------------------------ Job + API

@pytest.mark.asyncio
async def test_remove_video_job(test_session, test_directory, async_client, video_factory):
    """The FileGroup follows the video into its audio-only life: same id, new suffix and mimetype."""
    from modules.videos.models import Video
    from wrolpi.files.models import FileGroup

    video = video_factory()
    video.file_group.length = 5
    test_session.commit()
    file_group_id = video.file_group_id
    video_path = video.video_path
    probes = FakeProbes(make_probe('h264', 'aac', 5.3), make_probe(None, 'mp3', 5.3, 'mp3'))

    async def fake_run_command(cmd, stdout_callback=None, **kwargs):
        if cmd[-1] != '-':
            shutil.copy(PROJECT_DIR / 'test/big_buck_bunny.mp3', cmd[-1])
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    with mock.patch('modules.videos.transcode.probe_for_verify', side_effect=probes), \
            mock.patch('wrolpi.cmd.run_command', side_effect=fake_run_command):
        job_id = transcode_video_job.enqueue(file_group_id=file_group_id, video_codec=REMOVE_VIDEO,
                                             audio_codec='mp3', container='mp3')
        record = await jobs.wait_for_job(job_id)

    assert record['status'] == jobs.COMPLETE, record
    new_path = video_path.with_suffix('.mp3')
    assert new_path.is_file() and not video_path.exists()

    test_session.expire_all()
    video = Video.find_by_file_group_id(test_session, file_group_id)
    assert video.video_path == new_path
    assert video.file_group.mimetype.startswith('audio/')
    assert test_session.query(FileGroup).count() == 1


@pytest.mark.asyncio
async def test_transcode_api_audio_file(async_client, test_session, audio_factory):
    """An audio file can be transcoded (audio codec / audio container); a video target is a 400."""
    audio = audio_factory()
    test_session.commit()

    request, response = await async_client.post(f'/api/videos/{audio.file_group_id}/transcode',
                                                content=json.dumps({'video_codec': 'h264', 'container': 'mp4'}))
    assert response.status == 400, response.json
    assert 'audio' in response.json['message'].lower() or 'audio' in response.json['error'].lower()

    request, response = await async_client.post(f'/api/videos/{audio.file_group_id}/transcode',
                                                content=json.dumps({'audio_codec': 'aac', 'container': 'm4a'}))
    assert response.status == 200, response.json
    jobs.cancel_job(response.json['job_id'])

    # Remove-video on an audio file is a no-op wording-wise but allowed (it is already audio).
    request, response = await async_client.post(f'/api/videos/{audio.file_group_id}/transcode',
                                                content=json.dumps({'video_codec': REMOVE_VIDEO, 'container': 'mp3'}))
    assert response.status == 200, response.json
    jobs.cancel_job(response.json['job_id'])


@pytest.mark.asyncio
async def test_transcode_api_remove_video_needs_audio_container(async_client, test_session, video_factory):
    video = video_factory()
    test_session.commit()
    request, response = await async_client.post(f'/api/videos/{video.file_group_id}/transcode',
                                                content=json.dumps({'video_codec': REMOVE_VIDEO, 'container': 'mp4'}))
    assert response.status == 400, response.json
    request, response = await async_client.post(f'/api/videos/{video.file_group_id}/transcode',
                                                content=json.dumps({'video_codec': REMOVE_VIDEO, 'audio_codec': 'aac',
                                                                    'container': 'm4a'}))
    assert response.status == 200, response.json
    jobs.cancel_job(response.json['job_id'])
