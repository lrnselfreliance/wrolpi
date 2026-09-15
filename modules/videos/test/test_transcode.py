import asyncio
import json
import pathlib
from unittest import mock

import pytest

from modules.videos.transcode import codecs_match, get_stream_codec_names, get_transcode_target, \
    transcode_can_satisfy_codecs, transcode_video_file, TRANSCODE_VIDEO_TARGETS, TRANSCODE_AUDIO_TARGETS, \
    verify_transcode_output
from wrolpi.cmd import CommandResult


def make_probe(vcodec='vp9', acodec='opus', duration=10.0, format_name='matroska,webm'):
    """An ffprobe result with one video and one audio stream."""
    streams = []
    if vcodec:
        streams.append({'codec_type': 'video', 'codec_name': vcodec})
    if acodec:
        streams.append({'codec_type': 'audio', 'codec_name': acodec})
    return {'streams': streams, 'format': {'format_name': format_name, 'duration': str(duration)}}


MP4 = 'mov,mp4,m4a,3gp,3g2,mj2'


class FakeProbes:
    """What ffprobe reports for the source (a vp9/opus webm) and for the transcode output.

    The default output is a full h264/aac transcode; a test that copies a stream sets `output`
    to what ffmpeg would really produce (a copied stream keeps the source codec)."""

    def __init__(self):
        self.source = make_probe('vp9', 'opus', 10.0)
        self.output = make_probe('h264', 'aac', 10.0, MP4)

    def __call__(self, path: pathlib.Path):
        # Sync: mock.patch wraps the async target in an AsyncMock, which awaits for us.
        if '.transcode.' in path.name:
            output = dict(self.output)
            if path.suffix != '.mp4' and output.get('format'):
                output['format'] = {**output['format'], 'format_name': 'matroska,webm'}
            return output
        return self.source


@pytest.fixture(autouse=True)
def mock_probe() -> FakeProbes:
    probes = FakeProbes()
    with mock.patch('modules.videos.transcode.probe_for_verify', side_effect=probes):
        yield probes


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


@pytest.mark.parametrize('video_codecs,audio_codecs,expected', [
    ([], [], True),  # Nothing to satisfy.
    (['h264'], [], True),
    (['av1', 'h264'], [], True),  # h264 is a target.
    (['av1'], [], False),  # No target can produce av1.
    (['h264'], ['aac'], True),
    (['h264'], ['vorbis'], False),  # No target can produce vorbis.
    ([], ['aac'], True),
    (['av1'], ['aac'], False),  # Both lists must be satisfiable.
])
def test_transcode_can_satisfy_codecs(video_codecs, audio_codecs, expected):
    """Strict is only suppressed by transcode when every preference list has a transcode target."""
    assert transcode_can_satisfy_codecs(video_codecs, audio_codecs) is expected


@pytest.mark.asyncio
async def test_transcode_video_file(test_directory, async_client):
    """A webm is transcoded to an mp4 with the same stem; the original file and its stale
    ffprobe sidecar are removed."""
    video_path = test_directory / 'video.webm'
    video_path.write_bytes(b'fake video data')
    sidecar = test_directory / 'video.ffprobe.json'
    sidecar.write_text(json.dumps({'streams': []}))

    async def fake_run_command(cmd, **kwargs):
        # ffmpeg writes the temporary output file.
        if cmd[-1] == '-':
            # The tail-decode check: nothing to write.
            return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=0)
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

    cmd = mock_run.call_args_list[0][0][0]
    assert '-c:v' in cmd and cmd[cmd.index('-c:v') + 1] == 'libx264'
    assert '-c:a' in cmd and cmd[cmd.index('-c:a') + 1] == 'aac'
    # Attached-picture streams are excluded; a missing audio stream is tolerated.
    assert '0:V:0' in cmd and '0:a:0?' in cmd


@pytest.mark.asyncio
async def test_transcode_video_file_copies_matching_stream(test_directory, async_client, mock_probe):
    """Only the mismatching stream is re-encoded; the other stream is copied."""
    video_path = test_directory / 'video.mp4'
    video_path.write_bytes(b'fake video data')
    mock_probe.output = make_probe('h264', 'opus', 10.0, MP4)  # Audio was copied.

    async def fake_run_command(cmd, **kwargs):
        if cmd[-1] == '-':
            # The tail-decode check: nothing to write.
            return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=0)
        pathlib.Path(cmd[-1]).write_bytes(b'transcoded data')
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    with mock.patch('modules.videos.transcode.run_command', side_effect=fake_run_command) as mock_run:
        result = await transcode_video_file(video_path, target_vcodec='h264', container='mp4')

    assert result == video_path, 'Same container: the file is replaced in place'
    cmd = mock_run.call_args_list[0][0][0]
    assert cmd[cmd.index('-c:v') + 1] == 'libx264'
    assert cmd[cmd.index('-c:a') + 1] == 'copy'


@pytest.mark.asyncio
async def test_transcode_video_file_forces_supported_container(test_directory, async_client, mock_probe):
    """webm cannot contain h264/aac; the container is forced to mp4."""
    video_path = test_directory / 'video.webm'
    video_path.write_bytes(b'fake video data')
    mock_probe.output = make_probe('h264', 'opus', 10.0, MP4)  # Audio was copied.

    async def fake_run_command(cmd, **kwargs):
        if cmd[-1] == '-':
            # The tail-decode check: nothing to write.
            return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=0)
        pathlib.Path(cmd[-1]).write_bytes(b'transcoded data')
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    with mock.patch('modules.videos.transcode.run_command', side_effect=fake_run_command):
        result = await transcode_video_file(video_path, target_vcodec='h264', container='webm')

    assert result == test_directory / 'video.mp4'


@pytest.mark.asyncio
async def test_transcode_video_file_failure_removes_tmp(test_directory, async_client):
    """A failed ffmpeg leaves the original file untouched and no temporary file behind."""
    video_path = test_directory / 'video.webm'
    video_path.write_bytes(b'fake video data')

    async def fake_run_command(cmd, **kwargs):
        if cmd[-1] == '-':
            # The tail-decode check: nothing to write.
            return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=0)
        pathlib.Path(cmd[-1]).write_bytes(b'partial data')
        return CommandResult(return_code=1, cancelled=False, stdout=b'', stderr=b'boom', elapsed=1)

    with mock.patch('modules.videos.transcode.run_command', side_effect=fake_run_command):
        with pytest.raises(RuntimeError):
            await transcode_video_file(video_path, target_vcodec='h264')

    assert video_path.is_file(), 'The original file must survive a failed transcode'
    assert not (test_directory / 'video.transcode.mp4').exists()
    assert not (test_directory / 'video.mp4').exists()


@pytest.mark.asyncio
async def test_transcode_video_file_disk_space_guard(test_directory, async_client):
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
async def test_transcode_lock_serializes(test_directory, async_client, mock_probe):
    """A transcode waits while `shared_ctx.transcode_lock` is held and releases it when done.

    This exercises the wait/release logic in-process; cross-process sharing of the lock is
    provided by Sanic's shared_ctx (created before workers fork) and is not proven here."""
    import asyncio
    from wrolpi.api_utils import api_app

    video_path = test_directory / 'video.webm'
    video_path.write_bytes(b'fake video data')
    mock_probe.output = make_probe('h264', 'opus', 10.0, MP4)  # Audio was copied.

    async def fake_run_command(cmd, **kwargs):
        if cmd[-1] == '-':
            # The tail-decode check: nothing to write.
            return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=0)
        pathlib.Path(cmd[-1]).write_bytes(b'transcoded data')
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    lock = api_app.shared_ctx.transcode_lock
    assert lock.acquire(block=False), 'Test could not take the transcode lock'
    released = False
    with mock.patch('modules.videos.transcode.run_command', side_effect=fake_run_command) as mock_run:
        task = asyncio.create_task(transcode_video_file(video_path, target_vcodec='h264'))
        try:
            await asyncio.sleep(0.5)
            mock_run.assert_not_called()  # Still waiting for the lock.
            assert not task.done()

            lock.release()
            released = True
            result = await asyncio.wait_for(task, timeout=10)
        finally:
            if not released:
                lock.release()
            if not task.done():
                task.cancel()

    assert result == test_directory / 'video.mp4'
    # One encode (plus the tail-decode verification of its output); the second waiter ran nothing yet.
    encodes = [c for c in mock_run.call_args_list if '-progress' in c[0][0]]
    assert len(encodes) == 1

    # The lock was released after the transcode.
    assert lock.acquire(block=False), 'transcode_video_file did not release the lock'
    lock.release()


@pytest.mark.asyncio
async def test_transcode_video_file_remux(test_directory, async_client, mock_probe):
    """No target codec is a remux: both streams are copied into the requested container."""
    video_path = test_directory / 'video.mkv'
    video_path.write_bytes(b'fake video data')
    mock_probe.output = make_probe('vp9', 'opus', 10.0, MP4)  # Both copied.

    async def fake_run_command(cmd, **kwargs):
        if cmd[-1] == '-':
            # The tail-decode check: nothing to write.
            return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=0)
        pathlib.Path(cmd[-1]).write_bytes(b'remuxed data')
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    with mock.patch('modules.videos.transcode.run_command', side_effect=fake_run_command) as mock_run:
        result = await transcode_video_file(video_path, container='mp4')

    assert result == test_directory / 'video.mp4' and result.is_file()
    assert not video_path.exists()
    cmd = mock_run.call_args_list[0][0][0]
    assert cmd[cmd.index('-c:v') + 1] == 'copy' and cmd[cmd.index('-c:a') + 1] == 'copy'
    assert '+faststart' in cmd



# ------------------------------------------------------------------ output verification

def test_verify_transcode_output_ok():
    source = make_probe('vp9', 'opus', 100.0)
    output = make_probe('h264', 'opus', 99.6, MP4)  # Audio copied; a frame trimmed.
    verify_transcode_output(source, output, target_vcodec='h264', target_acodec=None, container='mp4')


def test_verify_transcode_output_remux_ok():
    source = make_probe('vp9', 'opus', 100.0)
    output = make_probe('vp9', 'opus', 100.0, MP4)
    verify_transcode_output(source, output, target_vcodec=None, target_acodec=None, container='mp4')


def test_verify_transcode_output_no_audio_ok():
    """A silent source has no audio to demand of the output."""
    source = make_probe('vp9', None, 100.0)
    output = make_probe('h264', None, 100.0, MP4)
    verify_transcode_output(source, output, target_vcodec='h264', target_acodec=None, container='mp4')


@pytest.mark.parametrize('output,message', [
    (make_probe('h264', 'aac', 50.0, MP4), 'duration'),  # Truncated.
    (make_probe('h264', None, 100.0, MP4), 'audio'),  # Lost the audio stream.
    (make_probe(None, 'aac', 100.0, MP4), 'video'),  # Lost the video stream.
    (make_probe('vp9', 'aac', 100.0, MP4), 'video codec'),  # Not re-encoded.
    (make_probe('h264', 'opus', 100.0, MP4), 'audio codec'),  # Not re-encoded.
    (make_probe('h264', 'aac', 100.0, 'matroska,webm'), 'container'),  # Wrong container.
    ({}, 'probe'),  # ffprobe could not read it.
])
def test_verify_transcode_output_rejects(output, message):
    source = make_probe('vp9', 'opus', 100.0)
    with pytest.raises(RuntimeError, match=message):
        verify_transcode_output(source, output, target_vcodec='h264', target_acodec='aac', container='mp4')


def test_verify_transcode_output_copied_stream_must_match_source():
    """A copied stream must come out with the source's codec."""
    source = make_probe('vp9', 'opus', 100.0)
    output = make_probe('h264', 'aac', 100.0, MP4)
    with pytest.raises(RuntimeError, match='audio codec'):
        verify_transcode_output(source, output, target_vcodec='h264', target_acodec=None, container='mp4')


def test_verify_transcode_output_duration_tolerance():
    """One second, or one percent, whichever is larger."""
    source = make_probe('vp9', 'opus', 10.0)
    verify_transcode_output(source, make_probe('h264', 'aac', 9.1, MP4), 'h264', 'aac', 'mp4')
    with pytest.raises(RuntimeError, match='duration'):
        verify_transcode_output(source, make_probe('h264', 'aac', 8.9, MP4), 'h264', 'aac', 'mp4')
    long_source = make_probe('vp9', 'opus', 40000.0)
    verify_transcode_output(long_source, make_probe('h264', 'aac', 39700.0, MP4), 'h264', 'aac', 'mp4')
    with pytest.raises(RuntimeError, match='duration'):
        verify_transcode_output(long_source, make_probe('h264', 'aac', 39500.0, MP4), 'h264', 'aac', 'mp4')


@pytest.mark.asyncio
async def test_transcode_video_file_rejects_truncated_output(test_directory, async_client, mock_probe):
    """ffmpeg exits 0 but the output is short: the original is kept, the output is removed."""
    video_path = test_directory / 'video.webm'
    video_path.write_bytes(b'fake video data')

    mock_probe.output = make_probe('h264', 'aac', 4.0, MP4)  # Source is 10s.

    async def fake_run_command(cmd, **kwargs):
        if cmd[-1] != '-':
            pathlib.Path(cmd[-1]).write_bytes(b'partial data')
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    with mock.patch('modules.videos.transcode.run_command', side_effect=fake_run_command):
        with pytest.raises(RuntimeError, match='duration'):
            await transcode_video_file(video_path, target_vcodec='h264', target_acodec='aac')

    assert video_path.read_bytes() == b'fake video data', 'The original must survive'
    assert not (test_directory / 'video.mp4').exists()
    assert not (test_directory / 'video.transcode.mp4').exists(), 'The bad output is removed'


@pytest.mark.asyncio
async def test_transcode_video_file_rejects_undecodable_tail(test_directory, async_client):
    """The last seconds of the output must decode cleanly, or the original is kept."""
    video_path = test_directory / 'video.webm'
    video_path.write_bytes(b'fake video data')
    tail_cmds = []

    async def fake_run_command(cmd, **kwargs):
        if cmd[-1] == '-':
            tail_cmds.append(cmd)
            return CommandResult(return_code=0, cancelled=False, stdout=b'',
                                 stderr=b'[h264 @ 0x1] Invalid NAL unit size', elapsed=1)
        pathlib.Path(cmd[-1]).write_bytes(b'transcoded data')
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    with mock.patch('modules.videos.transcode.run_command', side_effect=fake_run_command):
        with pytest.raises(RuntimeError, match='decode'):
            await transcode_video_file(video_path, target_vcodec='h264', target_acodec='aac')

    assert video_path.read_bytes() == b'fake video data'
    assert not (test_directory / 'video.transcode.mp4').exists()
    # The check decodes only the tail of the temporary output, discarding the frames.
    assert len(tail_cmds) == 1
    cmd = tail_cmds[0]
    assert '-sseof' in cmd and cmd[cmd.index('-sseof') + 1].startswith('-')
    assert str(cmd[cmd.index('-i') + 1]).endswith('video.transcode.mp4')
    assert cmd[cmd.index('-f') + 1] == 'null'


@pytest.mark.asyncio
async def test_transcode_video_file_cancel_removes_tmp(test_directory, async_client):
    """A cancelled encode (a Job's run_command raises CancelledError, a BaseException) must still
    remove the temporary output and leave the original."""
    video_path = test_directory / 'video.webm'
    video_path.write_bytes(b'fake video data')

    async def fake_run_command(cmd, **kwargs):
        pathlib.Path(cmd[-1]).write_bytes(b'partial data')
        raise asyncio.CancelledError('killed')

    with mock.patch('modules.videos.transcode.run_command', side_effect=fake_run_command):
        with pytest.raises(asyncio.CancelledError):
            await transcode_video_file(video_path, target_vcodec='h264')

    assert video_path.read_bytes() == b'fake video data'
    assert not (test_directory / 'video.transcode.mp4').exists(), 'The partial output must be removed'
