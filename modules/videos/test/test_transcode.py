import json
import pathlib
from unittest import mock

import pytest

from modules.videos.transcode import codecs_match, get_stream_codec_names, get_transcode_target, \
    transcode_video_file, TRANSCODE_VIDEO_TARGETS, TRANSCODE_AUDIO_TARGETS
from wrolpi.cmd import CommandResult


def test_get_stream_codec_names():
    """Embedded thumbnail streams (mjpeg/png) are not video."""
    data = {'streams': [
        {'codec_type': 'video', 'codec_name': 'vp9'},
        {'codec_type': 'video', 'codec_name': 'mjpeg'},
        {'codec_type': 'audio', 'codec_name': 'opus'},
    ]}
    assert get_stream_codec_names(data, 'video') == ['vp9']
    assert get_stream_codec_names(data, 'audio') == ['opus']
    assert get_stream_codec_names({}, 'video') == []
    assert get_stream_codec_names(None, 'video') == []


@pytest.mark.parametrize('video_codecs,audio_codecs,expected', [
    ([], [], (True, True)),  # No preference always matches.
    (['vp9'], ['opus'], (True, True)),
    (['h264'], [], (False, True)),
    (['h264', 'vp9'], [], (True, True)),  # Any preferred codec matches.
    ([], ['aac'], (True, False)),
    (['h264'], ['aac'], (False, False)),
])
def test_codecs_match(video_codecs, audio_codecs, expected):
    data = {'streams': [
        {'codec_type': 'video', 'codec_name': 'vp9'},
        {'codec_type': 'audio', 'codec_name': 'opus'},
    ]}
    assert codecs_match(data, video_codecs, audio_codecs) == expected


def test_codecs_match_missing_stream():
    """A missing stream matches: an audio-only file has no video stream to enforce."""
    data = {'streams': [{'codec_type': 'audio', 'codec_name': 'mp3'}]}
    assert codecs_match(data, ['h264'], ['mp3']) == (True, True)


def test_get_transcode_target():
    """The first preferred codec which is a supported target is the target."""
    assert get_transcode_target(['h264', 'vp9'], TRANSCODE_VIDEO_TARGETS) == 'h264'
    assert get_transcode_target(['vp9', 'h264'], TRANSCODE_VIDEO_TARGETS) == 'h264'
    assert get_transcode_target(['vp9', 'av1'], TRANSCODE_VIDEO_TARGETS) is None
    assert get_transcode_target([], TRANSCODE_VIDEO_TARGETS) is None
    assert get_transcode_target(['opus', 'aac'], TRANSCODE_AUDIO_TARGETS) == 'opus'


@pytest.mark.asyncio
async def test_transcode_video_file(test_directory):
    """A webm is transcoded to an mp4 with the same stem; the original file and its stale
    ffprobe sidecar are removed."""
    video_path = test_directory / 'video.webm'
    video_path.write_bytes(b'fake video data')
    sidecar = test_directory / 'video.ffprobe.json'
    sidecar.write_text(json.dumps({'streams': []}))

    async def fake_run_command(cmd, **kwargs):
        # ffmpeg writes the temporary output file.
        pathlib.Path(cmd[-1]).write_bytes(b'transcoded data')
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    with mock.patch('modules.videos.transcode.run_command', side_effect=fake_run_command) as mock_run:
        result = await transcode_video_file(video_path, target_vcodec='h264', target_acodec='aac',
                                            container='mp4')

    assert result == test_directory / 'video.mp4'
    assert result.is_file() and result.read_bytes() == b'transcoded data'
    assert not video_path.exists(), 'The original webm should be deleted'
    assert not sidecar.exists(), 'The stale ffprobe sidecar should be deleted'
    assert not (test_directory / 'video.transcode.mp4').exists(), 'The temporary file should be renamed'

    cmd = mock_run.call_args[0][0]
    assert '-c:v' in cmd and cmd[cmd.index('-c:v') + 1] == 'libx264'
    assert '-c:a' in cmd and cmd[cmd.index('-c:a') + 1] == 'aac'


@pytest.mark.asyncio
async def test_transcode_video_file_copies_matching_stream(test_directory):
    """Only the mismatching stream is re-encoded; the other stream is copied."""
    video_path = test_directory / 'video.mp4'
    video_path.write_bytes(b'fake video data')

    async def fake_run_command(cmd, **kwargs):
        pathlib.Path(cmd[-1]).write_bytes(b'transcoded data')
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    with mock.patch('modules.videos.transcode.run_command', side_effect=fake_run_command) as mock_run:
        result = await transcode_video_file(video_path, target_vcodec='h264', container='mp4')

    assert result == video_path, 'Same container: the file is replaced in place'
    cmd = mock_run.call_args[0][0]
    assert cmd[cmd.index('-c:v') + 1] == 'libx264'
    assert cmd[cmd.index('-c:a') + 1] == 'copy'


@pytest.mark.asyncio
async def test_transcode_video_file_forces_supported_container(test_directory):
    """webm cannot contain h264/aac; the container is forced to mp4."""
    video_path = test_directory / 'video.webm'
    video_path.write_bytes(b'fake video data')

    async def fake_run_command(cmd, **kwargs):
        pathlib.Path(cmd[-1]).write_bytes(b'transcoded data')
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    with mock.patch('modules.videos.transcode.run_command', side_effect=fake_run_command):
        result = await transcode_video_file(video_path, target_vcodec='h264', container='webm')

    assert result == test_directory / 'video.mp4'


@pytest.mark.asyncio
async def test_transcode_video_file_failure_removes_tmp(test_directory):
    """A failed ffmpeg leaves the original file untouched and no temporary file behind."""
    video_path = test_directory / 'video.webm'
    video_path.write_bytes(b'fake video data')

    async def fake_run_command(cmd, **kwargs):
        pathlib.Path(cmd[-1]).write_bytes(b'partial data')
        return CommandResult(return_code=1, cancelled=False, stdout=b'', stderr=b'boom', elapsed=1)

    with mock.patch('modules.videos.transcode.run_command', side_effect=fake_run_command):
        with pytest.raises(RuntimeError):
            await transcode_video_file(video_path, target_vcodec='h264')

    assert video_path.is_file(), 'The original file must survive a failed transcode'
    assert not (test_directory / 'video.transcode.mp4').exists()
    assert not (test_directory / 'video.mp4').exists()


@pytest.mark.asyncio
async def test_transcode_video_file_disk_space_guard(test_directory):
    """Transcoding is refused when the disk is nearly full."""
    video_path = test_directory / 'video.webm'
    video_path.write_bytes(b'fake video data' * 1000)

    fake_usage = mock.Mock(free=video_path.stat().st_size)  # Less than 1.5x the source size.
    with mock.patch('modules.videos.transcode.shutil.disk_usage', return_value=fake_usage), \
            mock.patch('modules.videos.transcode.run_command') as mock_run:
        with pytest.raises(RuntimeError, match='free space'):
            await transcode_video_file(video_path, target_vcodec='h264')
    mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_transcode_video_file_requires_target():
    with pytest.raises(RuntimeError, match='target codec'):
        await transcode_video_file(pathlib.Path('/tmp/video.mp4'))
