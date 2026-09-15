import asyncio
import os
import pathlib
import shutil
from typing import List, Optional, Tuple, Callable

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
TRANSCODE_CONTAINERS = ('mp4', 'mkv')

TRANSCODE_TIMEOUT = 4 * 60 * 60  # A long video on a Raspberry Pi can take hours.

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
                               duration: Optional[float] = None) -> pathlib.Path:
    """Transcode a video file in place (same stem, possibly a new container extension).

    Only one transcode runs at a time machine-wide (across all Sanic workers); this call waits
    for its turn.  Only the stream(s) with a target are re-encoded; the other stream is copied.
    The output is written to a temporary file in the same directory, then atomically renamed over
    the final path.  The original file is deleted if the extension changed.  Returns the final
    path.

    When run inside a Job (see `wrolpi.jobs`), ffmpeg's output is captured into the Job log and, if
    `duration` (seconds) is known, progress is reported to the Job.

    @raise RuntimeError: when ffmpeg fails, or there is not enough free disk space.
    """
    if not FFMPEG_BIN:
        raise RuntimeError('ffmpeg was not found')
    # No target for either stream is a remux: both streams are copied into the (new) container
    # with faststart.  Cheap, and what a user wants when only the container is wrong.
    if container not in TRANSCODE_CONTAINERS:
        logger.info(f'Forcing mp4 container for transcode of {video_path} ({container} is not supported)')
        container = 'mp4'

    lock = await _acquire_transcode_lock()
    try:
        return await _transcode_video_file(video_path, target_vcodec, target_acodec, container, duration)
    finally:
        lock.release()


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


async def _transcode_video_file(video_path: pathlib.Path, target_vcodec: Optional[str],
                                target_acodec: Optional[str], container: str,
                                duration: Optional[float] = None) -> pathlib.Path:
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

    video_args = TRANSCODE_VIDEO_TARGETS[target_vcodec] if target_vcodec else ('-c:v', 'copy')
    audio_args = TRANSCODE_AUDIO_TARGETS[target_acodec] if target_acodec else ('-c:a', 'copy')

    final_path = video_path.with_suffix(f'.{container}')
    tmp_path = video_path.with_suffix(f'.transcode.{container}')
    # 0:V:0 excludes attached-picture streams (embedded thumbnails); 0:a:0? tolerates a video
    # with no audio stream.
    cmd = (FFMPEG_BIN, '-y',
           '-i', video_path,
           '-map', '0:V:0', '-map', '0:a:0?',
           *video_args,
           *audio_args,
           '-movflags', '+faststart',
           # Machine-readable progress on stdout (the human progress line is suppressed).
           '-nostats', '-progress', 'pipe:1',
           str(tmp_path))
    logger.warning(f'Transcoding {video_path} to {final_path} (video={target_vcodec}, audio={target_acodec})')
    try:
        job = get_current_job()
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
    if final_path != video_path:
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
    """@raise ValueError: when the request cannot be transcoded.  No codec at all is a remux."""
    if video_codec and video_codec not in TRANSCODE_VIDEO_TARGETS:
        raise ValueError(f'Cannot transcode video to {video_codec!r}; supported: {sorted(TRANSCODE_VIDEO_TARGETS)}')
    if audio_codec and audio_codec not in TRANSCODE_AUDIO_TARGETS:
        raise ValueError(f'Cannot transcode audio to {audio_codec!r}; supported: {sorted(TRANSCODE_AUDIO_TARGETS)}')
    if container not in TRANSCODE_CONTAINERS:
        raise ValueError(f'Unsupported container {container!r}; supported: {TRANSCODE_CONTAINERS}')


@register_job('transcode_video')
async def transcode_video_job(file_group_id: int, video_codec: Optional[str] = None,
                              audio_codec: Optional[str] = None, container: str = 'mp4') -> dict:
    """Transcode a Video's file, then re-index it so the FileGroup reflects the new file.

    Run as a Job (`transcode_video_job.enqueue(...)`) so the user can watch and cancel it."""
    from modules.videos.models import Video
    from wrolpi.files.lib import get_mimetype
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

    final_path = await transcode_video_file(video_path, video_codec, audio_codec, container, duration=duration)

    # Point the existing FileGroup at the new file *before* refreshing.  A refresh which finds a
    # new filename on disk would delete this FileGroup and create another, losing tags and history.
    with get_db_session(commit=True) as session:
        video = Video.find_by_file_group_id(session, file_group_id)
        file_group = video.file_group
        if final_path != video_path:
            file_group.files = [
                {**i, 'path': final_path.name, 'mimetype': get_mimetype(final_path)}
                if i['path'] == video_path.name else i
                for i in file_group.files
            ]
            file_group.primary_path = final_path
            file_group.mimetype = get_mimetype(final_path)
        # The streams changed: the modeler must ffprobe the file again.
        video.ffprobe_json = None
        file_group.indexed = False

    job_id = file_worker.queue_refresh([final_path], send_events=False)
    await file_worker.wait_for_job(job_id)

    return {'path': str(get_relative_to_media_directory(final_path))}
