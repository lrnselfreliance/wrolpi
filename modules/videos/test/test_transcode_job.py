"""Tests for the transcode Job and its API (see `wrolpi.jobs`)."""
import json
import pathlib
import shutil
from unittest import mock

import pytest

from modules.videos.models import Video
from modules.videos.transcode import make_ffmpeg_progress_parser, transcode_video_job
from wrolpi import jobs
from wrolpi.cmd import CommandResult
from wrolpi.files.models import FileGroup
from wrolpi.vars import PROJECT_DIR

MP4 = 'mov,mp4,m4a,3gp,3g2,mj2'


@pytest.fixture(autouse=True)
def mock_probe():
    """The output probe agrees with what the Job asked for (targets or copied source codecs)."""

    async def probe(path: pathlib.Path):
        # The test video is h264/aac; a copied stream keeps that, a target replaces it.
        fmt = MP4 if path.suffix == '.mp4' else 'matroska,webm'
        return {'streams': [{'codec_type': 'video', 'codec_name': 'h264'},
                            {'codec_type': 'audio', 'codec_name': 'aac'}],
                'format': {'format_name': fmt, 'duration': '5.3'}}

    with mock.patch('modules.videos.transcode.probe_for_verify', side_effect=probe):
        yield


def test_make_ffmpeg_progress_parser():
    """`-progress pipe:1` lines are converted to whole-percent progress, reported only on change."""
    reported = []
    parse = make_ffmpeg_progress_parser(100.0, reported.append)
    parse('frame=12')  # Ignored.
    parse('out_time_us=25000000')
    parse('out_time_us=25400000')  # Still 25%, not reported again.
    parse('out_time_ms=50000000')  # Older ffmpeg key, also microseconds.
    parse('out_time_us=garbage')
    parse('out_time_us=250000000')  # Clamped to 100.
    assert reported == [25, 50, 100]

    # No duration: nothing can be reported.
    reported.clear()
    make_ffmpeg_progress_parser(None, reported.append)('out_time_us=25000000')
    assert reported == []


@pytest.mark.asyncio
async def test_transcode_video_job(test_session, test_directory, async_client, video_factory):
    """The transcode Job runs ffmpeg inside the Job (log + progress captured) and re-indexes the
    Video so its FileGroup points at the new file."""
    video_path = test_directory / 'videos/NO CHANNEL/movie.webm'
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video = video_factory(with_video_file=video_path)
    video.file_group.length = 10
    test_session.commit()
    file_group_id = video.file_group_id

    async def fake_run_command(cmd, stdout_callback=None, **kwargs):
        # ffmpeg reports progress on stdout, then writes the temporary output file.  The output
        # must be a real video: the refresh would otherwise drop the Video model (mimetype changed).
        stdout_callback('out_time_us=5000000')
        if cmd[-1] == '-':
            # The tail-decode check: nothing to write.
            return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=0)
        shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', cmd[-1])
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'ffmpeg version fake', elapsed=1)

    # In tests the file refresh is drained inline by the waiter, inside the Job's task, so its
    # (many) log lines land in the Job log too and could push the early lines out of the tail.
    with mock.patch('wrolpi.cmd.run_command', side_effect=fake_run_command), \
            mock.patch.object(jobs, 'JOB_LOG_LINES', 10_000):
        job_id = transcode_video_job.enqueue(description='Transcode movie.webm', file_group_id=file_group_id,
                                             video_codec='h264', audio_codec='aac', container='mp4')
        record = await jobs.wait_for_job(job_id)

    assert record['status'] == jobs.COMPLETE, record
    assert record['result'] == {'path': 'videos/NO CHANNEL/movie.mp4'}
    assert 'out_time_us=5000000' in record['log'], 'ffmpeg stdout is in the Job log'
    assert 'ffmpeg version fake' in record['log'], 'ffmpeg stderr is in the Job log'
    assert any('Transcoding' in i for i in record['log']), 'logger output is in the Job log'

    assert not video_path.exists()
    assert (test_directory / 'videos/NO CHANNEL/movie.mp4').is_file()

    test_session.expire_all()
    # The same FileGroup (tags, history) now points at the mp4; no new FileGroup was created.
    video = Video.find_by_file_group_id(test_session, file_group_id)
    assert video.video_path == test_directory / 'videos/NO CHANNEL/movie.mp4'
    assert video.file_group.primary_path == test_directory / 'videos/NO CHANNEL/movie.mp4'
    assert video.file_group.mimetype == 'video/mp4'
    # The modeler probed the new file and wrote a fresh sidecar; the webm is gone.
    assert sorted(i['path'] for i in video.file_group.files) == ['movie.ffprobe.json', 'movie.mp4']
    assert video.ffprobe_json, 'ffprobe ran again on the new file'
    assert video.file_group.indexed is True, 'The refresh re-modeled the Video'
    assert test_session.query(FileGroup).count() == 1


@pytest.mark.asyncio
async def test_transcode_video_job_remux(test_session, test_directory, async_client, video_factory):
    """No target codec is a remux: both streams are copied into the requested container."""
    video_path = test_directory / 'videos/NO CHANNEL/movie.mkv'
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video = video_factory(with_video_file=video_path)
    test_session.commit()

    async def fake_run_command(cmd, stdout_callback=None, **kwargs):
        if cmd[-1] == '-':
            # The tail-decode check: nothing to write.
            return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=0)
        shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', cmd[-1])
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    with mock.patch('wrolpi.cmd.run_command', side_effect=fake_run_command) as mock_run:
        job_id = transcode_video_job.enqueue(file_group_id=video.file_group_id, container='mp4')
        record = await jobs.wait_for_job(job_id)

    assert record['status'] == jobs.COMPLETE, record
    cmd = mock_run.call_args_list[0][0][0]
    assert cmd[cmd.index('-c:v') + 1] == 'copy' and cmd[cmd.index('-c:a') + 1] == 'copy'
    assert '+faststart' in cmd
    assert not video_path.exists()
    assert (test_directory / 'videos/NO CHANNEL/movie.mp4').is_file()


@pytest.mark.asyncio
async def test_transcode_video_job_failure(test_session, test_directory, async_client, video_factory):
    """A failed ffmpeg fails the Job and leaves the original file in place."""
    video = video_factory()
    video_path = video.video_path

    async def fake_run_command(cmd, stdout_callback=None, **kwargs):
        return CommandResult(return_code=1, cancelled=False, stdout=b'', stderr=b'Conversion failed!', elapsed=1)

    with mock.patch('wrolpi.cmd.run_command', side_effect=fake_run_command):
        job_id = transcode_video_job.enqueue(file_group_id=video.file_group_id, video_codec='h264')
        record = await jobs.wait_for_job(job_id)

    assert record['status'] == jobs.FAILED
    assert 'Conversion failed!' in record['error']
    assert video_path.is_file()


@pytest.mark.asyncio
async def test_video_transcode_api(async_client, test_session, video_factory, wrol_mode_fixture):
    """The transcode endpoint validates the request, then queues a Job."""
    video = video_factory()
    test_session.commit()

    # Unsupported target.
    request, response = await async_client.post(f'/api/videos/{video.file_group_id}/transcode',
                                                content=json.dumps({'video_codec': 'av1'}))
    assert response.status == 400
    # Unknown video.
    request, response = await async_client.post('/api/videos/999999/transcode',
                                                content=json.dumps({'video_codec': 'h264'}))
    assert response.status == 404
    assert jobs.get_jobs() == [], 'Nothing was queued'

    request, response = await async_client.post(f'/api/videos/{video.file_group_id}/transcode',
                                                content=json.dumps({'video_codec': 'h264', 'audio_codec': 'aac'}))
    assert response.status == 200, response.json
    job_id = response.json['job_id']
    record = jobs.get_job(job_id)
    assert record['status'] == jobs.PENDING
    assert record['name'] == 'transcode_video'
    assert record['description'] == f'Transcode {video.video_path.name}'
    assert record['kwargs'] == {'file_group_id': video.file_group_id, 'video_codec': 'h264',
                                'audio_codec': 'aac', 'container': 'mp4', 'fragmented': False}
    # Do not run it (ffmpeg); cancel instead.
    jobs.cancel_job(job_id)

    # No codec at all is allowed: a container-only remux.
    request, response = await async_client.post(f'/api/videos/{video.file_group_id}/transcode',
                                                content=json.dumps({'container': 'mkv'}))
    assert response.status == 200, response.json
    assert jobs.get_job(response.json['job_id'])['kwargs'] == {
        'file_group_id': video.file_group_id, 'video_codec': None, 'audio_codec': None, 'container': 'mkv', 'fragmented': False}
    jobs.cancel_job(response.json['job_id'])

    # WROL mode forbids modifying files.
    await wrol_mode_fixture(True)
    request, response = await async_client.post(f'/api/videos/{video.file_group_id}/transcode',
                                                content=json.dumps({'video_codec': 'h264'}))
    assert response.status == 403
    await wrol_mode_fixture(False)


@pytest.mark.asyncio
async def test_transcode_video_job_wrol_mode(test_session, test_directory, async_client, video_factory,
                                             wrol_mode_fixture):
    """A transcode queued before WROL Mode was enabled must not run: the Job fails, ffmpeg is never
    started, and the file is untouched."""
    video = video_factory()
    video_path = video.video_path
    before = video_path.read_bytes()

    job_id = transcode_video_job.enqueue(file_group_id=video.file_group_id, video_codec='h264')
    await wrol_mode_fixture(True)
    try:
        with mock.patch('wrolpi.cmd.run_command') as mock_run:
            record = await jobs.wait_for_job(job_id)
    finally:
        await wrol_mode_fixture(False)

    assert record['status'] == jobs.FAILED, record
    assert 'WROL Mode' in record['error']
    mock_run.assert_not_called()
    assert video_path.read_bytes() == before


@pytest.mark.asyncio
async def test_transcode_video_job_retargets_before_deleting(test_session, test_directory, async_client,
                                                              video_factory):
    """When the suffix changes, the FileGroup is pointed at the new file (and committed) while the
    old file still exists; the old file is deleted only afterwards.  A crash in between then leaves
    both files with the database pointing at a real one."""
    from modules.videos import transcode as transcode_module

    video_path = test_directory / 'videos/NO CHANNEL/movie.webm'
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video = video_factory(with_video_file=video_path)
    test_session.commit()
    seen = {}

    real_retarget = transcode_module.retarget_file_group

    def spy_retarget(file_group_id, old_path, new_path):
        seen['old_exists'] = old_path.exists()
        seen['new_exists'] = new_path.exists()
        real_retarget(file_group_id, old_path, new_path)
        test_session.expire_all()
        seen['db_primary'] = Video.find_by_file_group_id(test_session, file_group_id).file_group.primary_path

    async def fake_run_command(cmd, stdout_callback=None, **kwargs):
        if cmd[-1] == '-':
            return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=0)
        shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', cmd[-1])
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    with mock.patch('wrolpi.cmd.run_command', side_effect=fake_run_command), \
            mock.patch.object(transcode_module, 'retarget_file_group', side_effect=spy_retarget):
        job_id = transcode_video_job.enqueue(file_group_id=video.file_group_id, video_codec='h264',
                                             audio_codec='aac', container='mp4')
        record = await jobs.wait_for_job(job_id)

    assert record['status'] == jobs.COMPLETE, record
    new_path = test_directory / 'videos/NO CHANNEL/movie.mp4'
    assert seen == {'old_exists': True, 'new_exists': True, 'db_primary': new_path}, seen
    assert not video_path.exists(), 'The old file is deleted once the database points at the new one'
    assert new_path.is_file()


@pytest.mark.asyncio
async def test_transcode_video_file_keep_original(test_directory, async_client):
    """`transcode_video_file(keep_original=True)` renames the output into place but leaves the
    original for the caller to delete once its records point at the new file."""
    from modules.videos.transcode import transcode_video_file
    video_path = test_directory / 'video.webm'
    video_path.write_bytes(b'fake video data')

    async def fake_run_command(cmd, **kwargs):
        if cmd[-1] == '-':
            return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=0)
        shutil.copy(PROJECT_DIR / 'test/big_buck_bunny_720p_1mb.mp4', cmd[-1])
        return CommandResult(return_code=0, cancelled=False, stdout=b'', stderr=b'', elapsed=1)

    with mock.patch('modules.videos.transcode.run_command', side_effect=fake_run_command):
        result = await transcode_video_file(video_path, target_vcodec='h264', target_acodec='aac',
                                            container='mp4', keep_original=True)

    assert result == test_directory / 'video.mp4' and result.is_file()
    assert video_path.read_bytes() == b'fake video data', 'The original is kept'


@pytest.mark.asyncio
async def test_video_transcode_api_fragmented(async_client, test_session, video_factory):
    """`fragmented` reaches the Job; it needs an mp4 container."""
    video = video_factory()
    test_session.commit()
    request, response = await async_client.post(f'/api/videos/{video.file_group_id}/transcode',
                                                content=json.dumps({'container': 'mp4', 'fragmented': True}))
    assert response.status == 200, response.json
    record = jobs.get_job(response.json['job_id'])
    assert record['kwargs']['fragmented'] is True
    assert record['description'].startswith('Remux')
    jobs.cancel_job(response.json['job_id'])

    request, response = await async_client.post(f'/api/videos/{video.file_group_id}/transcode',
                                                content=json.dumps({'container': 'mkv', 'fragmented': True}))
    assert response.status == 400
