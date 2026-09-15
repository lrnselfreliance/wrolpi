import asyncio
import os
import pathlib
import shutil
from typing import List, Optional, Tuple, Callable

from modules.videos.common import ffprobe_json, ffmpeg_video_complete_async
from wrolpi.captions import FFMPEG_BIN
from wrolpi.cmd import run_command
from wrolpi.common import logger, get_relative_to_media_directory, wrol_mode_enabled
from wrolpi.db import get_db_session
from wrolpi.jobs import register_job, get_current_job
from wrolpi.vars import DEFAULT_FILE_PERMISSIONS, PYTEST

logger = logger.getChild(__name__)

# How often a waiting worker re-checks the machine-wide transcode lock.
TRANSCODE_LOCK_POLL_SECONDS = 0.1 if PYTEST else 10

# ffprobe `codec_name` values that satisfy each user-selectable codec preference.
FFPROBE_VIDEO_CODEC_NAMES = {
    'h264': {'h264'},
    'hevc': {'hevc', 'h265'},
    'vp9': {'vp9'},
    'av1': {'av1'},
    'vp8': {'vp8'},
}
FFPROBE_AUDIO_CODEC_NAMES = {
    'aac': {'aac'},
    'opus': {'opus'},
    'mp3': {'mp3'},
    'vorbis': {'vorbis'},
}

# Codecs which can be a transcode *target*, mapped to their ffmpeg encoder args.  VP9/AV1/HEVC are
# omitted because software encoding them is impractically slow on a Raspberry Pi.
TRANSCODE_VIDEO_TARGETS = {
    'h264': ('-c:v', 'libx264', '-preset', 'medium', '-crf', '23'),
}
TRANSCODE_AUDIO_TARGETS = {
    'aac': ('-c:a', 'aac', '-b:a', '192k'),
    'opus': ('-c:a', 'libopus', '-b:a', '128k'),
    'mp3': ('-c:a', 'libmp3lame', '-q:a', '2'),
}

# Containers that can hold an h264/aac transcode result.  webm cannot.
TRANSCODE_CONTAINERS = ('mp4', 'mkv')  # For output with a video stream.
# For audio-only output: the video stream removed (`REMOVE_VIDEO`), or an audio-only source.
TRANSCODE_AUDIO_CONTAINERS = ('m4a', 'ogg', 'mp3')
# ffprobe codec names each audio container can hold without re-encoding.
# Ordered: `default_audio_container` picks the first container that holds a codec, so the most
# specific container comes first (mp3 fits in m4a too, but an .mp3 is what a user expects).
AUDIO_CONTAINER_CODECS = {
    'mp3': {'mp3'},
    'ogg': {'opus', 'vorbis', 'flac'},
    'm4a': {'aac', 'mp3', 'alac'},
}
# `target_vcodec` value meaning "drop the video stream"; the output is an audio file.
REMOVE_VIDEO = 'none'
# ffprobe's `format_name` token for each container (mkv reports "matroska,webm").
CONTAINER_FORMAT_NAMES = {'mp4': 'mp4', 'mkv': 'matroska', 'm4a': 'm4a', 'ogg': 'ogg', 'mp3': 'mp3'}
# `-movflags +faststart` is an mp4-muxer option; other muxers warn about it.
FASTSTART_CONTAINERS = ('mp4', 'm4a')


def default_audio_container(codec: Optional[str]) -> str:
    """The natural audio container for a codec: what a player expects from the suffix."""
    for container, codecs in AUDIO_CONTAINER_CODECS.items():
        if codec in codecs:
            return container
    return 'm4a'

TRANSCODE_TIMEOUT = 4 * 60 * 60  # A long video on a Raspberry Pi can take hours.

# Output verification (see `verify_transcode_output`): the output's duration may differ from the
# source by this much before it is considered truncated.  Muxers trim a frame or two; a truncated
# file is off by minutes.
DURATION_TOLERANCE_SECONDS = 1.0
DURATION_TOLERANCE_RATIO = 0.01

# Transcoding writes a whole new copy of the video next to the original.
MINIMUM_FREE_SPACE_RATIO = 1.5


def get_stream_codec_names(ffprobe_data: dict, codec_type: str) -> List[str]:
    """Return the codec_name of every stream of the given type ('video' or 'audio').

    Embedded thumbnails appear as mjpeg/png video streams; they are not real video."""
    streams = (ffprobe_data or {}).get('streams') or []
    names = [s.get('codec_name') for s in streams if s.get('codec_type') == codec_type]
    if codec_type == 'video':
        names = [i for i in names if i not in ('mjpeg', 'png')]
    return [i for i in names if i]


def codecs_match(ffprobe_data: dict, video_codecs: List[str], audio_codecs: List[str]) \
        -> Tuple[bool, bool]:
    """Return (video matches, audio matches) for the codec preferences.

    An empty preference list always matches.  A missing stream also matches (an audio-only file
    has no video stream to enforce)."""
    video_match = True
    if video_codecs:
        names = get_stream_codec_names(ffprobe_data, 'video')
        if names:
            acceptable = set().union(*(FFPROBE_VIDEO_CODEC_NAMES.get(i, {i}) for i in video_codecs))
            video_match = any(i in acceptable for i in names)
    audio_match = True
    if audio_codecs:
        names = get_stream_codec_names(ffprobe_data, 'audio')
        if names:
            acceptable = set().union(*(FFPROBE_AUDIO_CODEC_NAMES.get(i, {i}) for i in audio_codecs))
            audio_match = any(i in acceptable for i in names)
    return video_match, audio_match


def get_transcode_target(preferences: List[str], targets: dict) -> Optional[str]:
    """The first preferred codec that is a supported transcode target, or None."""
    for codec in preferences or []:
        if codec in targets:
            return codec
    return None


def transcode_can_satisfy_codecs(video_codecs: List[str], audio_codecs: List[str]) -> bool:
    """True only if transcoding could produce a preferred codec for every non-empty preference
    list.  When False, enabling transcode cannot guarantee the preferences (e.g. av1-only), so
    strict_codecs must still be honored."""
    return ((not video_codecs or get_transcode_target(video_codecs, TRANSCODE_VIDEO_TARGETS) is not None)
            and (not audio_codecs or get_transcode_target(audio_codecs, TRANSCODE_AUDIO_TARGETS) is not None))


async def _acquire_transcode_lock():
    """Block (asynchronously) until this process holds the machine-wide transcode lock.

    Polled with sleep instead of a blocking acquire so a multi-hour ffmpeg hold elsewhere does
    not stall this worker's event loop."""
    from wrolpi.api_utils import api_app
    lock = api_app.shared_ctx.transcode_lock
    if not lock.acquire(block=False):
        logger.info('Waiting for another transcode to finish')
        while not lock.acquire(block=False):
            await asyncio.sleep(TRANSCODE_LOCK_POLL_SECONDS)
    return lock


async def transcode_video_file(video_path: pathlib.Path,
                               target_vcodec: Optional[str] = None,
                               target_acodec: Optional[str] = None,
                               container: str = 'mp4',
                               duration: Optional[float] = None,
                               keep_original: bool = False) -> pathlib.Path:
    """Transcode a video file in place (same stem, possibly a new container extension).

    Only one transcode runs at a time machine-wide (across all Sanic workers); this call waits
    for its turn.  Only the stream(s) with a target are re-encoded; the other stream is copied.
    The output is written to a temporary file in the same directory, then atomically renamed over
    the final path.  The original file is deleted if the extension changed, unless
    `keep_original`: a caller with database records pointing at the original must retarget them
    first, then delete it (see `transcode_video_job`), so a crash never leaves the records pointing
    at a deleted file.  Returns the final path.

    When run inside a Job (see `wrolpi.jobs`), ffmpeg's output is captured into the Job log and, if
    `duration` (seconds) is known, progress is reported to the Job.

    @raise RuntimeError: when ffmpeg fails, or there is not enough free disk space.
    """
    if not FFMPEG_BIN:
        raise RuntimeError('ffmpeg was not found')
    # No target for either stream is a remux: both streams are copied into the (new) container.
    # `target_vcodec=REMOVE_VIDEO` (or an audio-only source) makes the output an audio file; see
    # `resolve_output`, which also settles an unsuitable container.

    lock = await _acquire_transcode_lock()
    try:
        return await _transcode_video_file(video_path, target_vcodec, target_acodec, container, duration,
                                           keep_original)
    finally:
        lock.release()


async def probe_for_verify(path: pathlib.Path) -> dict:
    """ffprobe a file for `verify_transcode_output`.  Separate so tests can replace it."""
    return await ffprobe_json(path)


def _format_names(probe: dict) -> List[str]:
    return str((probe.get('format') or {}).get('format_name') or '').split(',')


def _duration(probe: dict) -> Optional[float]:
    try:
        return float((probe.get('format') or {}).get('duration'))
    except (TypeError, ValueError):
        return None


def verify_transcode_output(source: dict, output: dict, target_vcodec: Optional[str],
                            target_acodec: Optional[str], container: str):
    """Compare ffprobe results of the source and the transcoded output; the output must be a
    complete rendition of the source before the source is replaced by it.

    Checks: the output parses (its index was written), it is in the requested container, it has a
    video stream (and an audio stream when the source has one), each stream's codec is the target
    or, when copied, the source's, and the duration matches within a tolerance.

    @raise RuntimeError: describing the first failed check.
    """
    if not output or output.get('streams') is None:
        raise RuntimeError('Transcode output could not be probed (no streams); its index may be missing')

    expected_format = CONTAINER_FORMAT_NAMES.get(container, container)
    if expected_format not in _format_names(output):
        raise RuntimeError(f'Transcode output container is {_format_names(output)}, expected {container}')

    source_video = get_stream_codec_names(source, 'video')
    source_audio = get_stream_codec_names(source, 'audio')
    output_video = get_stream_codec_names(output, 'video')
    output_audio = get_stream_codec_names(output, 'audio')

    audio_only = target_vcodec == REMOVE_VIDEO or not source_video
    if audio_only:
        if output_video:
            raise RuntimeError(f'Transcode output still has a video stream ({output_video[0]})')
        if not output_audio:
            raise RuntimeError('Transcode output has no audio stream')
    else:
        if not output_video:
            raise RuntimeError('Transcode output has no video stream')
        if source_audio and not output_audio:
            raise RuntimeError('Transcode output has no audio stream, but the source has one')
        expected_video = target_vcodec or (source_video[0] if source_video else None)
        if expected_video and output_video[0] != expected_video:
            raise RuntimeError(f'Transcode output video codec is {output_video[0]}, expected {expected_video}')
    expected_audio = target_acodec or (source_audio[0] if source_audio else None)
    if output_audio and expected_audio and output_audio[0] != expected_audio:
        raise RuntimeError(f'Transcode output audio codec is {output_audio[0]}, expected {expected_audio}')

    source_duration, output_duration = _duration(source), _duration(output)
    if source_duration is not None:
        if output_duration is None:
            raise RuntimeError('Transcode output has no duration')
        tolerance = max(DURATION_TOLERANCE_SECONDS, DURATION_TOLERANCE_RATIO * source_duration)
        if abs(source_duration - output_duration) > tolerance:
            raise RuntimeError(
                f'Transcode output duration is {output_duration:.1f}s, source is {source_duration:.1f}s')


async def _verify_tail_decodes(path: pathlib.Path, runner: Callable):
    """The same completeness check a download gets (`ffmpeg_video_complete`), as a hard failure.

    @raise RuntimeError: when the tail of `path` does not decode cleanly."""
    ok, errors = await ffmpeg_video_complete_async(path, runner=runner)
    if not ok:
        raise RuntimeError(f'Transcode output failed to decode: {errors[-2000:] or "ffmpeg exited non-zero"}')


def make_ffmpeg_progress_parser(duration: Optional[float], set_progress: Callable[[float], None]) \
        -> Callable[[str], None]:
    """Return a callback for `ffmpeg -progress pipe:1` stdout lines which reports percent complete.

    ffmpeg emits `out_time_us=<microseconds>` (older builds: `out_time_ms`, also microseconds)."""
    last = [-1]

    def parse(line: str):
        if not duration or duration <= 0:
            return
        key, sep, value = line.partition('=')
        if not sep or key not in ('out_time_us', 'out_time_ms'):
            return
        try:
            seconds = int(value) / 1_000_000
        except ValueError:
            return
        percent = int(min(100.0, max(0.0, 100.0 * seconds / duration)))
        if percent != last[0]:
            last[0] = percent
            set_progress(percent)

    return parse


def resolve_output(source_probe: dict, target_vcodec: Optional[str], target_acodec: Optional[str],
                   container: str) -> Tuple[bool, str]:
    """Decide whether the output is audio-only and which container it gets.

    Audio-only when the video is to be removed, or the source has no video stream.  An audio
    container that cannot hold the (copied or target) audio codec is refused; a video container
    asked for an audio-only output is replaced by the codec's natural one.

    @raise RuntimeError: when the request cannot be satisfied by this source."""
    source_video = get_stream_codec_names(source_probe, 'video')
    source_audio = get_stream_codec_names(source_probe, 'audio')

    if target_vcodec and target_vcodec != REMOVE_VIDEO and not source_video:
        raise RuntimeError(f'Cannot transcode video to {target_vcodec}: the file has no video stream')

    audio_only = target_vcodec == REMOVE_VIDEO or not source_video
    if not audio_only:
        if container not in TRANSCODE_CONTAINERS:
            logger.info(f'Forcing mp4 container ({container} cannot hold a video stream)')
            container = 'mp4'
        return False, container

    if not source_audio:
        raise RuntimeError('Cannot produce an audio file: the source has no audio stream')
    effective_acodec = target_acodec or source_audio[0]
    if container not in TRANSCODE_AUDIO_CONTAINERS:
        container = default_audio_container(effective_acodec)
        logger.info(f'Using {container} container for audio-only output ({effective_acodec})')
    elif effective_acodec not in AUDIO_CONTAINER_CODECS[container]:
        raise RuntimeError(
            f'{effective_acodec} audio cannot be stored in {container}; choose another container or codec')
    return True, container


async def _transcode_video_file(video_path: pathlib.Path, target_vcodec: Optional[str],
                                target_acodec: Optional[str], container: str,
                                duration: Optional[float] = None, keep_original: bool = False) -> pathlib.Path:
    """The ffmpeg work of `transcode_video_file`; the caller holds the transcode lock."""
    # Notify here, after the lock: the wait for another transcode can last hours, and the user
    # should hear "Transcoding" only when this file's work actually begins.
    try:
        from wrolpi.events import Events
        Events.send_user_notify(f'Transcoding {video_path.name}')
    except Exception:
        # Events are best-effort; never let them break a download.
        logger.debug(f'Failed to send transcode event for {video_path}', exc_info=True)

    source_size = video_path.stat().st_size
    free = shutil.disk_usage(video_path.parent).free
    if free < MINIMUM_FREE_SPACE_RATIO * source_size:
        raise RuntimeError(
            f'Not enough free space to transcode {video_path} ({free} bytes free, source is {source_size} bytes)')

    # Probed before ffmpeg: the command depends on the source's streams, and verification compares
    # against the file as it was.
    source_probe = await probe_for_verify(video_path)
    audio_only, container = resolve_output(source_probe, target_vcodec, target_acodec, container)

    audio_args = TRANSCODE_AUDIO_TARGETS[target_acodec] if target_acodec else ('-c:a', 'copy')
    if audio_only:
        # `-vn` also drops embedded cover art; the audio stream is required.
        map_args = ('-map', '0:a:0', '-vn')
        video_args = ()
    else:
        # 0:V:0 excludes attached-picture streams (embedded thumbnails); 0:a:0? tolerates a video
        # with no audio stream.
        map_args = ('-map', '0:V:0', '-map', '0:a:0?')
        video_args = TRANSCODE_VIDEO_TARGETS[target_vcodec] if target_vcodec else ('-c:v', 'copy')
    faststart_args = ('-movflags', '+faststart') if container in FASTSTART_CONTAINERS else ()

    final_path = video_path.with_suffix(f'.{container}')
    tmp_path = video_path.with_suffix(f'.transcode.{container}')
    cmd = (FFMPEG_BIN, '-y',
           '-i', video_path,
           *map_args,
           *video_args,
           *audio_args,
           *faststart_args,
           # Machine-readable progress on stdout (the human progress line is suppressed).
           '-nostats', '-progress', 'pipe:1',
           str(tmp_path))
    logger.warning(f'Transcoding {video_path} to {final_path} (video={target_vcodec}, audio={target_acodec})')
    try:
        job = get_current_job()
        runner = job.run_command if job else run_command
        if job:
            # Inside a Job: ffmpeg's output lands in the Job log and progress is reported.
            result = await job.run_command(cmd, cwd=video_path.parent, timeout=TRANSCODE_TIMEOUT,
                                           stdout_callback=make_ffmpeg_progress_parser(duration, job.set_progress))
        else:
            result = await run_command(cmd, cwd=video_path.parent, timeout=TRANSCODE_TIMEOUT)
        if result.return_code != 0:
            raise RuntimeError(
                f'ffmpeg exited with {result.return_code} while transcoding {video_path}:'
                f'\n{result.stderr.decode()[-2000:]}')

        # The original is only replaced by a complete output: compare probes, then prove the tail
        # decodes.  A failure here leaves the original untouched.
        logger.info(f'Verifying transcode output {tmp_path}')
        output_probe = await probe_for_verify(tmp_path)
        verify_transcode_output(source_probe, output_probe, target_vcodec, target_acodec, container)
        await _verify_tail_decodes(tmp_path, runner)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    # fsync before the rename: a Pi losing power after the rename must not be left with a
    # truncated final file.
    fd = os.open(tmp_path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

    # The old ffprobe sidecar describes the old streams.
    video_path.with_suffix('.ffprobe.json').unlink(missing_ok=True)
    tmp_path.rename(final_path)
    if final_path != video_path and not keep_original:
        video_path.unlink()
    final_path.chmod(DEFAULT_FILE_PERMISSIONS)

    # fsync the directory so the rename itself is durable.
    fd = os.open(video_path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError:
        pass  # Some filesystems refuse directory fsync; the rename is still atomic.
    finally:
        os.close(fd)
    return final_path


def validate_transcode_request(video_codec: Optional[str], audio_codec: Optional[str], container: str):
    """@raise ValueError: when the request cannot be transcoded.  No codec at all is a remux;
    `video_codec=REMOVE_VIDEO` drops the video stream and needs an audio container."""
    if video_codec and video_codec != REMOVE_VIDEO and video_codec not in TRANSCODE_VIDEO_TARGETS:
        raise ValueError(f'Cannot transcode video to {video_codec!r}; supported: {sorted(TRANSCODE_VIDEO_TARGETS)}')
    if audio_codec and audio_codec not in TRANSCODE_AUDIO_TARGETS:
        raise ValueError(f'Cannot transcode audio to {audio_codec!r}; supported: {sorted(TRANSCODE_AUDIO_TARGETS)}')
    containers = TRANSCODE_CONTAINERS + TRANSCODE_AUDIO_CONTAINERS
    if container not in containers:
        raise ValueError(f'Unsupported container {container!r}; supported: {containers}')
    if video_codec == REMOVE_VIDEO and container not in TRANSCODE_AUDIO_CONTAINERS:
        raise ValueError(f'Removing the video needs an audio container ({TRANSCODE_AUDIO_CONTAINERS}), not {container}')
    if container in TRANSCODE_AUDIO_CONTAINERS:
        if video_codec and video_codec != REMOVE_VIDEO:
            raise ValueError(f'A video stream cannot be stored in {container}; remove the video or choose a video container')
        if audio_codec and audio_codec not in AUDIO_CONTAINER_CODECS[container]:
            raise ValueError(f'{audio_codec} audio cannot be stored in {container}; '
                             f'it holds {sorted(AUDIO_CONTAINER_CODECS[container])}')


def retarget_file_group(file_group_id: int, old_path: pathlib.Path, new_path: pathlib.Path):
    """Point a Video's FileGroup at the transcoded file and mark it for re-modeling.  Committed."""
    from modules.videos.models import Video
    from wrolpi.files.lib import get_mimetype

    with get_db_session(commit=True) as session:
        video = Video.find_by_file_group_id(session, file_group_id)
        file_group = video.file_group
        if new_path != old_path:
            mimetype = get_mimetype(new_path)
            file_group.files = [
                {**i, 'path': new_path.name, 'mimetype': mimetype} if i['path'] == old_path.name else i
                for i in file_group.files
            ]
            file_group.primary_path = new_path
            file_group.mimetype = mimetype
        # The streams changed: the modeler must ffprobe the file again.
        video.ffprobe_json = None
        file_group.indexed = False


@register_job('transcode_video')
async def transcode_video_job(file_group_id: int, video_codec: Optional[str] = None,
                              audio_codec: Optional[str] = None, container: str = 'mp4') -> dict:
    """Transcode a Video's file, then re-index it so the FileGroup reflects the new file.

    Run as a Job (`transcode_video_job.enqueue(...)`) so the user can watch and cancel it."""
    from modules.videos.models import Video
    from wrolpi.files.worker import file_worker

    # The API refuses to queue in WROL Mode; this catches a Job queued before it was enabled.
    if wrol_mode_enabled():
        raise RuntimeError('Cannot transcode while WROL Mode is enabled')

    validate_transcode_request(video_codec, audio_codec, container)

    with get_db_session() as session:
        video = Video.find_by_file_group_id(session, file_group_id)
        video_path = video.video_path
        duration = video.file_group.length
        if not video_path or not video_path.is_file():
            raise RuntimeError(f'Video file does not exist: {video_path}')

    # The original is kept until the database points at the new file (below).
    final_path = await transcode_video_file(video_path, video_codec, audio_codec, container, duration=duration,
                                            keep_original=True)

    # Point the existing FileGroup at the new file *before* deleting the original and *before*
    # refreshing.  A crash after the delete would leave the database pointing at a missing file;
    # a refresh which finds a new filename on disk would delete this FileGroup and create another,
    # losing tags and history.
    retarget_file_group(file_group_id, video_path, final_path)
    if final_path != video_path:
        video_path.unlink(missing_ok=True)

    job_id = file_worker.queue_refresh([final_path], send_events=False)
    await file_worker.wait_for_job(job_id)

    return {'path': str(get_relative_to_media_directory(final_path))}
